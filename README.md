# Skill Alexa — **Incluir Estoque** (Python + Flask)

Aplicação **Python/Flask** que expõe um endpoint para a *Alexa Skill* **Incluir Estoque**.  
A skill guia o usuário por voz para **inserir itens em um estoque** e grava os dados em um **SQL Server** (host padrão: `192.168.3.145`).  
O serviço roda em **dev** com Flask e em **produção** com **Waitress**.

## Fluxo
1. Invocar: “incluir estoque”  
2. Alexa coleta **material**, **quantidade** e **setor** com confirmação  
3. API grava no SQL Server (cria localização se necessário)  
4. Alexa confirma a inclusão

## Endpoints
- `GET /health` — health-check
- `POST /alexa` — webhook da Skill (LaunchRequest/IntentRequest)

## Principais arquivos
- `app.py` — endpoints, diálogo, execução com Waitress
- `consulta.py` — conexão `pyodbc` e funções `buscar_localizacao`/`incluir_estoque`

## Estrutura sugerida
```
.
├── app.py
├── consulta.py
├── requirements.txt
├── .env
└── images/
    └── simulator.png
```

## Pré‑requisitos
- Python 3.12+
- Driver ODBC 17 do SQL Server
- Banco SQL Server acessível
- Variáveis no `.env`

## Instalação
```bash
git clone <seu-repo>.git
cd <seu-repo>
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` (exemplo):
```
Flask
python-dotenv
pyodbc
waitress
```

## Configuração (.env)
```env
HOST=0.0.0.0
PORT=5000
DEBUG=1

THREADS=4
CONNECTION_LIMIT=100
CHANNEL_TIMEOUT=30

DB_SERVER=192.168.3.145
DB_NAME=SEU_BANCO
DB_USER=SEU_USUARIO
DB_PASSWORD=SUA_SENHA
```

## Execução
**Dev (Flask):**
```bash
# DEBUG=1
python app.py
```
**Produção (Waitress):**
```bash
# DEBUG=0
python app.py
```

## Banco (modelo mínimo)
```sql
CREATE TABLE dbo.localizacoes (
  id    INT IDENTITY(1,1) PRIMARY KEY,
  setor INT NOT NULL UNIQUE
);

CREATE TABLE dbo.produtos (
  id             INT IDENTITY(1,1) PRIMARY KEY,
  nome           NVARCHAR(200) NOT NULL,
  quantidade     INT NULL,
  preco          DECIMAL(18,2) NOT NULL DEFAULT 0,
  localizacao_id INT NULL REFERENCES dbo.localizacoes(id)
);
```

> O código grava o `nome` do material em **maiúsculas** e soma `quantidade` se já existir.

## Dicas
- Não versione `.env`
- Use túnel seguro/HTTPS para publicar o webhook
- Valide o *Application ID* da Alexa em produção
- Logs em produção: `logs/app.log` com **RotatingFileHandler**
