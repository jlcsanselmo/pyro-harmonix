import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from api.services.coverage_pilot import summarize_coverage


class Command(BaseCommand):
    help = "Evaluate paired regional coverage evidence from a local CSV of disjoint pieces."

    def add_arguments(self, parser):
        parser.add_argument("pieces", type=Path)
        parser.add_argument("--minimum-joint-fraction", type=float, default=0.8)

    def handle(self, *args, **options):
        try:
            with options["pieces"].open(encoding="utf-8-sig", newline="") as file:
                cells = summarize_coverage(csv.DictReader(file), options["minimum_joint_fraction"])
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise CommandError(str(error)) from error
        if not cells:
            raise CommandError("A coverage study requires paired mask and geolocation evidence.")
        self.stdout.write(json.dumps({
            "version": "paired_coverage_pilot_v1",
            "minimum_joint_fraction": options["minimum_joint_fraction"],
            "cells": cells,
        }, indent=2, allow_nan=False))
