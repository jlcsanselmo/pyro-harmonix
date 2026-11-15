# PyroHarmonix

WebGIS para explorar atividade de fogo no Brasil e em áreas selecionadas pelo usuário, usando observações Standard Processing MODIS e VIIRS-SNPP da NASA FIRMS.

## Executar com Docker

Requisito: Docker Desktop com Docker Compose v2. Crie o arquivo local de configuração e informe sua chave gratuita NASA FIRMS (não a publique nem a envie pelo chat):

```bash
cp .env.example .env
```

Edite `.env` e substitua `FIRMS_MAP_KEY`. Solicite uma chave em <https://firms.modaps.eosdis.nasa.gov/api/area/>. Depois execute:

```bash
docker compose up --build
```

Abra <http://localhost:8081> (ou a porta definida em `WEB_PORT`). PostgreSQL, API, interface e o worker de sincronização executam em containers; nenhum dado é enviado pelo navegador para a NASA. Os dados ficam nos volumes Docker `postgres_data` e `fire_data`. O volume antigo SQLite `fire_data` é preservado e seus registros são copiados para PostgreSQL na inicialização.

Sem `FIRMS_MAP_KEY`, o aplicativo continua abrindo e o worker mostra `AGUARDANDO CHAVE FIRMS`. Após editar `.env`, recrie o serviço para aplicar a variável:

```bash
docker compose up -d --build --force-recreate firms-sync
```

## Coleta automática e harmonização

O serviço `firms-sync` carrega os últimos cinco anos do Brasil, salva o progresso por sensor e retoma do último intervalo após reiniciar. A API FIRMS limita cada consulta a cinco dias; o worker consulta os produtos em intervalos de até cinco dias, com pausa entre solicitações, e atualiza diariamente os cinco dias mais recentes para incorporar revisões do Standard Processing. O progresso e erros aparecem no painel.

Para outra localidade, informe um retângulo nas coordenadas da área e datas dentro da janela dos últimos cinco anos e use **Buscar dados FIRMS**. Essas solicitações entram em uma fila persistente processada pelo worker, sem iniciar uma carga global automática. Cada pedido aceita no máximo 20° por lado e cinco anos; a fila comporta até cinco pedidos pendentes. A consulta é feita para os mesmos produtos, salva os dados brutos e harmoniza os dias selecionados. A coleta contínua e a atualização diária permanecem limitadas ao Brasil.

Nesta versão são usados `MODIS_SP` (a partir de 2000-11) e `VIIRS_SNPP_SP` (a partir de 2012). O pipeline:

1. Persiste as detecções de origem e seus atributos FIRMS no PostgreSQL.
2. Agrega as detecções por célula H3 de resolução 8 (aproximadamente 1 km²) e dia UTC.
3. Na janela comum carregada dos últimos cinco anos, calcula um fator MODIS/VIIRS por mês do ano, usando as observações do Brasil, se ambos os produtos tiverem ao menos 500 detecções naquele mês.
4. Em células/dias com os dois sensores, calcula a média entre a contagem MODIS e a contagem VIIRS ajustada; onde só há um sensor, usa sua contagem (ajustada quando calibrada).

Esse fator é uma calibração empírica exploratória para comparação de contagens, **não** uma harmonização científica validada nem uma estimativa de área queimada. Quando a janela não tem dados suficientes, o produto é marcado como não calibrado e usa fator 1. Os originais continuam armazenados para permitir reprocessamento. Para evitar misturar as diferenças de órbita de múltiplas plataformas VIIRS, esta primeira versão usa somente VIIRS-SNPP; NOAA-20/21, NRT, mascaramento de nuvens, biome-stratificação e validação independente ainda não estão incluídos.

O worker respeita a janela de até cinco dias por solicitação e pausa pelo menos três segundos entre chamadas. A NASA documenta um limite de 5.000 transações por intervalo de 10 minutos; falhas deixam o checkpoint intacto e são tentadas novamente.

## Importar dados manualmente

O upload CSV permanece disponível para dados harmonizados externos. Baixe o modelo pelo aplicativo ou em <http://localhost:8081/api/template.csv>. Colunas aceitas:

| Coluna | Obrigatória | Descrição |
| --- | --- | --- |
| `latitude` | Sim | Latitude decimal, de -90 a 90 |
| `longitude` | Sim | Longitude decimal, de -180 a 180 |
| `acq_datetime` | Sim* | Data/hora ISO 8601, por exemplo `2024-08-12T03:00:00Z` |
| `acq_date` | Sim* | Data `AAAA-MM-DD`; pode ser usada no lugar de `acq_datetime` |
| `acq_time` | Não | Hora `HH:MM` quando `acq_date` é usada |
| `sensor` | Não | Sensor ou origem para rastreabilidade |
| `confidence` | Não | Confiança fornecida pelo produto |
| `frp` | Não | Potência radiativa do fogo, valor não negativo |

Cada linha representa uma detecção e recebe peso 1. Importações são aditivas; registros duplicados são ignorados. Arquivos UTF-8 de até 10 MB e 200.000 linhas são aceitos. Os filtros iniciais mostram os últimos cinco anos e o retângulo do Brasil; ajuste as datas e coordenadas para delimitar uma área. O botão de download exporta todos os pontos que correspondem aos filtros, mesmo quando o mapa limita a quantidade de células exibidas.

## API

- `GET /api/health/` — estado do serviço.
- `GET /api/ingestion-status/` — estado do worker e checkpoints por produto.
- `GET /api/area-requests/` e `POST /api/area-requests/create/` — consultar a fila e solicitar coleta de uma área delimitada.
- `GET /api/analytics/` — totais, calendário mensal e comparação com a mediana do mesmo mês em anos anteriores.
- `GET /api/hotspots/` — hotspots para o mapa; o parâmetro `limit` limita os marcadores (máximo 10.000).
- `GET /api/hotspots.csv` — exportação CSV sem limite de linhas.
- `POST /api/upload/` — importar arquivo multipart com campo `file`.

Os endpoints de consulta aceitam `start`, `end`, `south`, `north`, `west` e `east`. A mediana histórica considera zeros nos anos sem detecções, desde o primeiro ano registrado até o ano anterior ao fim do período selecionado. Se o intervalo selecionado começa dentro do mês final, a comparação usa a mesma janela de dias do mês nos anos anteriores.

## Desenvolvimento local sem Docker

Backend (Python 3.12+). Sem `DB_ENGINE=postgresql`, o Django usa SQLite para desenvolvimento e testes:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py test
python manage.py runserver
```

Frontend (Node.js 22+): em outro terminal, execute `cd frontend`, `npm ci` e `npm run dev`. Para desenvolvimento, configure o proxy da Vite para a API Docker ou execute o frontend atrás do Nginx do Compose.

## Escopo e interpretação

O valor da mediana é uma comparação descritiva de contagens mensais por área, não uma previsão. A camada de fundo usa OpenStreetMap e requer acesso à internet. Para implantação pública, configure `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `DJANGO_DEBUG=false`, hosts permitidos, autenticação no upload e um servidor de aplicação adequado.
