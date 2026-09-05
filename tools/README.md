# tools/

Ferramentas descartáveis do passo zero do projeto brindes-automa-tiny. Não fazem
parte da aplicação (backend/frontend) — servem apenas para coletar amostras reais
das APIs dos quatro fornecedores e gerar um relatório de campos que vai orientar
o modelo de dados do backend.

## Setup

```bash
cd tools
poetry install
```

As credenciais já estão em `.env` (não versionado). `.env.example` documenta as
chaves esperadas sem valores.

## Uso

Coletar amostras de todos os fornecedores (pula os que já têm amostra salva):

```bash
poetry run python fetch_samples.py
```

Coletar de um fornecedor específico:

```bash
poetry run python fetch_samples.py --fornecedor xbz
```

Forçar nova coleta mesmo com amostra existente:

```bash
poetry run python fetch_samples.py --fornecedor asia --force
```

A XBZ tem limite de 24 chamadas/dia compartilhado com o cliente final — o script
pede confirmação explícita (digitar `sim`) antes de chamar essa API.

A Só Marcas é pulada automaticamente enquanto `SOMARCAS_USUARIO`/`SOMARCAS_SENHA`
estiverem vazios no `.env` (credenciais ainda não fornecidas pelo cliente).

Gerar o relatório a partir das amostras salvas:

```bash
poetry run python analyze_samples.py
```

O relatório é impresso no terminal e salvo em `../samples/RELATORIO.md`. Ele não
contém preços reais nem o JSON bruto, apenas estrutura, tipos e percentuais de
preenchimento dos campos.

## Fornecedores

| Fornecedor | Autenticação | Observação |
|---|---|---|
| xbz | cnpj + token na query string | limite de 24 chamadas/dia |
| asia | api_key + secret_key, multipart/form-data | só páginas 1–3 são coletadas |
| somarcas | Basic Auth (usuario:senha em base64) | credenciais pendentes do cliente |
| spot | fluxo de token: AuthenticateClient → chamadas → CloseSession | token expira, sempre reautentica |
