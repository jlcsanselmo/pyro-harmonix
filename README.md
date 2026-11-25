# PyroHarmonix

WebGIS para explorar a atividade de fogo registrada por MODIS-Aqua e VIIRS-Suomi-NPP. O mapa, o calendário e as séries ajudam a comparar períodos e regiões com base nas observações FIRMS disponíveis. A versão 1.0 consolida a aplicação e cinco etapas de investigação regional.

## Origem e equipe

O projeto foi desenvolvido pela equipe **ThermalGrid** para a etapa local de Ribeirão Preto do **NASA Space Apps Challenge 2026**, conforme os materiais de participação do projeto. A participação no evento e o uso de dados públicos da NASA são créditos de origem. [Evento local](https://www.spaceappschallenge.org/2026/local-events/ribeirao-preto/) · [Apresentação arquivada](docs/pyroharmonix-spaceapps-demo.pdf)

## Funcionalidades

- Mapa, calendário, série mensal e comparação com a mediana de anos com registros.
- Filtro por retângulo e período, exportação CSV e importação de CSV harmonizado.
- Processamento de observações disponíveis na base local e fila persistente para solicitações FIRMS por região e ano.
- Metadados de procedência do índice, fatores regionais e acompanhamento da ingestão.
- Visualizador contextual do episódio de 2024 com imagens NASA Worldview/GIBS, separado das camadas georreferenciadas do mapa.

## Método e resultados

Em produção, centros das detecções são indexados em H3 e agrupados por célula H3 7, dia UTC e turno. Na região elegível, VIIRS recebe um fator mensal regularizado na escala Aqua. A série `detection_conditioned_v1` usa a média quando os dois sensores registram e mantém a contribuição elegível quando apenas um registra. Um silêncio em FIRMS tem cobertura desconhecida.

Na caixa bruta Altinópolis–Pitangueiras, em 2019–2024, a regra somou **2.282,55 equivalentes Aqua**, frente a **1.530 registros Aqua** e **1.529,63 equivalentes** da regra histórica com zero. A diferença frente a Aqua foi de **49,2%**. Em anos retidos, a regularização na união dos registros obteve WAPE de **21,98% mensal** e **15,07% anual** para contagem, frente ao Aqua registrado. Cada resultado pertence ao seu desenho de avaliação.

O pipeline orbital separado leu **sete duplas reais**, com seis utilizáveis no cenário principal de 55°, H3 7, 80% de área comum e 60 min. Em 2019, a política M13 chegou a Jaccard de **0,50** em seu próprio suporte, e o Jaccard ficou em **0** no suporte fixo. A fusão condicionada à cobertura continua experimental. [Relatório final](docs/FINAL_SCIENTIFIC_REPORT.md) · [Métricas sem arredondamento](docs/data/final-scientific-summary.json)

O índice descreve atividade registrada, em equivalentes Aqua. A identificação de incêndios individuais, área queimada, previsão, acurácia independente e transferência universal da calibração exigem outros desenhos e referências. [Limitações](docs/LIMITATIONS.md)

## Arquitetura e fontes

| Componente | Implementação |
| --- | --- |
| WebGIS | React, Vite e Leaflet, com mapa-base OpenStreetMap |
| API e processamento | Python 3.12, Django, biblioteca H3, servidor de desenvolvimento no Compose |
| Persistência | PostgreSQL 16 no Compose, SQLite para desenvolvimento e reprodução isolada |
| Ingestão | Processo Django separado para fila FIRMS, checkpoints e arquivo de respostas CSV |
| Serviços | Docker Compose, Nginx para frontend estático e proxy da API |
| Ciência orbital | Scripts CLI separados com NumPy, pyhdf, NetCDF4, pyproj, Shapely e Matplotlib |

A ingestão usa FIRMS Standard Processing. O teste orbital usa MYD14/MYD03 C6.1 e VNP14IMG/VNP03IMG C2, catalogados no Earthdata CMR. As imagens de contexto são creditadas ao NASA Global Imagery Browse Services (GIBS/ESDIS). [Arquitetura](docs/ARCHITECTURE.md) · [FIRMS](https://firms.modaps.eosdis.nasa.gov/) · [CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) · [NASA Worldview](https://worldview.earthdata.nasa.gov/) · [Atribuição OpenStreetMap](https://www.openstreetmap.org/copyright)

## Instalação com Docker

Use Docker Desktop ou Docker Engine com Compose v2. Na raiz, crie `.env` a partir de `.env.example` se ainda não existir. Configure `POSTGRES_PASSWORD` e `DJANGO_SECRET_KEY` locais. Ajuste `WEB_PORT` e deixe `WEB_BIND_ADDR=127.0.0.1` para uso no computador local. `FIRMS_MAP_KEY` é necessário somente para novas solicitações FIRMS. O backfill contínuo nacional fica desligado por padrão.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Configure os valores no arquivo local antes de iniciar.
docker compose config --quiet
docker compose up -d --build
```

- WebGIS em <http://localhost:8081>.
- API de saúde em <http://localhost:8081/api/health/>.
- Acompanhamento do trabalhador com `docker compose logs -f firms-sync`.

| Variáveis | Uso |
| --- | --- |
| `WEB_BIND_ADDR`, `WEB_PORT` | Endereço e porta do WebGIS no host, com padrão 127.0.0.1:8081 |
| `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_SECRET_KEY` | Modo, hosts permitidos e segredo do Django |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Configuração do banco e da conexão dos contêineres |
| `FIRMS_MAP_KEY`, `FIRMS_BRAZIL_BACKFILL_ENABLED` | Credencial de coleta e ativação explícita do backfill nacional |

O volume PostgreSQL preserva a base entre reinícios. `docker compose down` encerra os serviços preservando volumes. Comece com base local ou use o roteiro de amostra para popular uma base temporária.

## Desenvolvimento e testes

No backend, use Python 3.12. Para execução sem Docker, assegure que `backend/data/` exista antes de migrar por SQLite. No frontend, use Node.js 22 conforme a imagem de build e o lockfile.

```powershell
# Terminal do backend
Set-Location backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
New-Item -ItemType Directory -Path data -Force | Out-Null
python manage.py migrate
python manage.py runserver
```

```powershell
# Terminal do frontend
Set-Location frontend
npm ci
npm run dev
npm run build
```

A integração frontend/API usa o proxy Nginx no Compose. O Vite isolado serve a interface de desenvolvimento. Para a suíte PostgreSQL completa, incluindo dependências orbitais, use os comandos do [roteiro de reprodução](docs/REPRODUCIBILITY.md). O roteiro também cobre as etapas científicas com os insumos já arquivados.

## Repositório e documentação

- `backend/api/` contém API, modelos, migrações, ingestão e harmonização.
- `backend/orbital_*.py` contém as entradas CLI dos experimentos orbitais.
- `frontend/` contém o WebGIS, dependências e configuração Nginx.
- `docs/data/` e `docs/assets/` preservam amostras, relatórios de máquina, mapas e figuras.
- `docs/paper/` contém o [rascunho de manuscrito](docs/paper/MANUSCRIPT_DRAFT.md) para revisão humana.

[Arquitetura](docs/ARCHITECTURE.md) · [Metodologia](docs/METHODOLOGY.md) · [Proveniência](docs/DATA_PROVENANCE.md) · [Índice científico](docs/SCIENTIFIC_ARTIFACT_INDEX.md) · [Notas da versão 1.0.0](docs/RELEASE_NOTES_V1.0.0.md) · [Histórico de alterações](CHANGELOG.md)

## Autoria e licença

O crédito do projeto é da equipe ThermalGrid, conforme o material de participação. O histórico Git registra as contribuições ao código. O repositório está sem arquivo de licença explícita para o código. Os termos e atribuições das fontes externas continuam aplicáveis aos respectivos dados e imagens. A lista de autores, afiliações e licença de distribuição fica sujeita à confirmação humana.
