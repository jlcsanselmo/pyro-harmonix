"""Bounded LAADS acquisition for the regional orbital pilot."""

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


LAADS = "ladsweb.modaps.eosdis.nasa.gov"
LP_DAAC = "data.lpdaac.earthdatacloud.nasa.gov"
LAADS_CLOUD = "data.laadsdaac.earthdatacloud.nasa.gov"
TRUSTED_REDIRECTS = frozenset((
    LAADS, LP_DAAC, LAADS_CLOUD, "urs.earthdata.nasa.gov",
    "d1nklfio7vscoe.cloudfront.net", "d13j1jds5ybppo.cloudfront.net",
))
MASK_PRODUCTS = frozenset(("MYD14", "VNP14IMG"))
EXPECTED = {
    "MYD14": ("061", "61", "hdf"),
    "MYD03": ("061", "61", "hdf"),
    "VNP14IMG": ("002", "5200", "nc"),
    "VNP03IMG": ("002", "5200", "nc"),
}
SIGNATURE = {"hdf": bytes.fromhex("0e031301"), "nc": bytes.fromhex("894844460d0a1a0a")}
MANIFEST_NAME = "granule-manifest.json"


def verified_plan(path):
    plan = json.loads(path.read_text(encoding="utf-8"))
    granules = plan["granules"]
    if len(granules) != 4 or {row["product"] for row in granules} != set(EXPECTED):
        raise ValueError("A pilot requires exactly one fire and geolocation granule per sensor.")
    acquisitions = {}
    for granule in granules:
        product = granule["product"]
        collection, archive, extension = EXPECTED[product]
        filename = granule["filename"]
        match = re.fullmatch(rf"{product}\.A(\d{{7}})\.(\d{{4}})\.{collection}\.\d{{13}}\.{extension}", filename)
        if match is None or granule["collection"] != collection:
            raise ValueError(f"Unexpected product collection or filename: {product}.")
        day, time = match.groups()
        target = f"https://{LAADS}/archive/allData/{archive}/{product}/{day[:4]}/{day[4:]}/{filename}"
        if granule["source_url"] != target:
            raise ValueError(f"Unexpected archive URL: {product}.")
        observed = datetime.fromisoformat(granule["acquisition_start_utc"].replace("Z", "+00:00"))
        if observed.utcoffset() is None or observed.utcoffset().total_seconds() != 0:
            raise ValueError(f"Acquisition metadata must be UTC: {product}.")
        if observed.strftime("%Y%j%H%M") != day + time or observed.date().isoformat() != plan["date"]:
            raise ValueError(f"Acquisition does not match filename and pilot date: {product}.")
        acquisitions[product] = observed
    if (acquisitions["MYD14"] != acquisitions["MYD03"]
            or acquisitions["VNP14IMG"] != acquisitions["VNP03IMG"]):
        raise ValueError("Fire and geolocation granules must have identical acquisition times per sensor.")
    cap = {"orbital_pilot_phase4_v1": 300, "orbital_pilot_phase5_v1": 250}.get(plan["version"], 225)
    if not 0 < plan["download_cap_mib"] <= cap:
        raise ValueError(f"The four-file pilot cannot exceed {cap} MiB.")
    return plan


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials are sent only to the fixed official archive, without forwarding.
        return None


class ArchiveRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin, token):
        self.origin = origin
        self.token = token

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destination = urllib.parse.urlsplit(newurl)
        if (destination.scheme != "https" or destination.hostname not in TRUSTED_REDIRECTS
                or destination.port not in (443, None) or destination.username or destination.password):
            return None
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is not None and self.token and destination.hostname == self.origin:
            redirected.add_unredirected_header("Authorization", f"Bearer {self.token}")
        return redirected


def _lp_daac_url(granule):
    collection = f"{granule['product']}.{granule['collection']}"
    filename = granule["filename"]
    return f"https://{LP_DAAC}/lp-prod-protected/{collection}/{Path(filename).stem}/{filename}"


def _cloud_url(granule):
    if granule["product"] in MASK_PRODUCTS:
        return _lp_daac_url(granule)
    return f"https://{LAADS_CLOUD}/prod-lads/{granule['product']}/{granule['filename']}"


def earthdata_token():
    token = os.environ.get("EARTHDATA_TOKEN", "").strip()
    if not token:
        path = os.environ.get("PYRO_EARTHDATA_TOKEN_FILE")
        if not path and os.environ.get("LOCALAPPDATA"):
            path = str(Path(os.environ["LOCALAPPDATA"]) / "PyroHarmonix" / "earthdata-token")
        if path and Path(path).is_file():
            try:
                token = Path(path).read_text(encoding="utf-8-sig").strip()
            except (OSError, UnicodeError):
                raise ValueError("Could not read the local Earthdata token file.") from None
    if token and re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", token) is None:
        raise ValueError("The local Earthdata token has an invalid format.")
    return token or None


def _checked_payload(path, granule, max_bytes=None):
    extension = EXPECTED[granule["product"]][2]
    with path.open("rb") as handle:
        if handle.read(len(SIGNATURE[extension])) != SIGNATURE[extension]:
            raise ValueError(f"Invalid binary signature: {granule['product']}.")
        size = path.stat().st_size
        if max_bytes is not None and size > max_bytes:
            raise ValueError("The pilot exceeded its download allowance.")
        handle.seek(0)
        digest = hashlib.file_digest(handle, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _sha256(handle)
    return {"bytes": size, "sha256": digest}


def _sha256(handle):
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _download(url, token, target, granule, remaining):
    origin = urllib.parse.urlsplit(url).hostname
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
    if token:
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    opener = urllib.request.build_opener(
        ArchiveRedirect(origin, token),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    temp = None
    try:
        with opener.open(request, timeout=90) as response:
            if response.status != 200 or response.headers.get("Content-Range"):
                raise ValueError("NASA did not return a complete response.")
            declared = response.headers.get("Content-Length")
            declared = int(declared) if declared else None
            if declared is not None and not 0 < declared <= remaining:
                raise ValueError("The response size is empty or exceeds the pilot allowance.")
            signature = SIGNATURE[EXPECTED[granule["product"]][2]]
            prefix = response.read(len(signature))
            if prefix != signature:
                raise ValueError(f"Invalid binary signature: {granule['product']}.")
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                temp = Path(output.name)
                output.write(prefix)
                received = len(prefix)
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    received += len(block)
                    if received > remaining:
                        raise ValueError("The pilot exceeded its download allowance.")
                    output.write(block)
                if declared is not None and received != declared:
                    raise ValueError("Incomplete NASA payload.")
        verified = _checked_payload(temp, granule)
        temp.replace(target)
        return verified
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def acquire(plan, directory, local_only=False, anonymous=False):
    token = None if local_only or anonymous else earthdata_token()
    remaining = int(plan["download_cap_mib"] * 1024 * 1024)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    manifest = directory / MANIFEST_NAME
    previous = {
        row["filename"]: row for row in verified_plan(manifest)["granules"]
    } if manifest.is_file() else {}
    for row in plan["granules"]:
        path = directory / row["filename"]
        if path.is_file():
            result = _checked_payload(path, row, remaining)
            prior = previous.get(row["filename"], {})
            if prior and any(prior.get(field) != result[field] for field in result):
                raise ValueError(f"Stored granule differs from its verified manifest: {row['product']}.")
            acquisition = prior.get("acquisition", "local")
            acquired_from = prior.get("acquired_from")
            if acquired_from not in (None, row["source_url"], _cloud_url(row)):
                raise ValueError(f"Unexpected prior acquisition URL: {row['product']}.")
        elif local_only:
            raise ValueError(f"Local granule missing: {row['filename']}.")
        elif not token and not anonymous:
            raise ValueError("Earthdata token required. Set EARTHDATA_TOKEN or use the documented local token file.")
        else:
            acquired_from = _cloud_url(row) if token else row["source_url"]
            try:
                result = _download(acquired_from, token, path, row, remaining)
            except urllib.error.HTTPError as error:
                raise ValueError(f"NASA returned HTTP {error.code} for {row['product']}.") from None
            except (urllib.error.URLError, TimeoutError):
                raise ValueError(f"Could not reach NASA for {row['product']}.") from None
            acquisition = "NASA_anonymous" if anonymous else "NASA_earthdata"
        remaining -= result["bytes"]
        records.append({**row, **result, "acquisition": acquisition, "acquired_from": acquired_from})
    report = {**plan, "granules": records}
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("directory", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local-only", action="store_true")
    mode.add_argument("--anonymous", action="store_true", help="Use only publicly retrievable archive URLs.")
    args = parser.parse_args()
    try:
        print(acquire(verified_plan(args.plan), args.directory, args.local_only, args.anonymous))
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
