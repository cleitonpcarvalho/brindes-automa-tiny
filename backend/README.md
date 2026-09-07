# backend/

Backend Django do brindes-automa-tiny. Passos 2 a 6 do projeto: fundação,
modelagem de dados, importação dos quatro fornecedores para o espelho
local, autenticação OAuth2 do Tiny, cadastro de produtos e atualização de
estoque no Tiny — corrigido no passo 6 contra o contrato oficial em
https://api-docs.erp.olist.com/api-reference/produtos/criar-produto.md
(substituindo o Swagger antigo usado no passo 5). **Falta só o frontend**
(passo 7).

## Stack

Django 5 + Django REST Framework, Postgres 16, Redis 7, Celery + Celery
Beat (worker e beat como serviços próprios), Docker Compose, dependências
via Poetry, imagem `python:3.12-slim`.

## Subir o ambiente

Na raiz do projeto (onde está o `docker-compose.yml`):

```bash
docker compose up --build
```

Isso sobe o Postgres e o backend Django em `http://localhost:8000`. As
variáveis de ambiente vêm do `.env` da raiz (veja `.env.example` para a
lista de chaves — nenhum valor sensível fica no código).

## Migrations

Com os containers no ar (outro terminal) ou via `docker compose run`:

```bash
docker compose exec backend python manage.py makemigrations
docker compose exec backend python manage.py migrate
```

Ou, se ainda não estiver rodando:

```bash
docker compose run --rm backend python manage.py migrate
```

## Criar o usuário administrador (admin + token da API)

```bash
docker compose exec backend python manage.py criar_admin_api --email admin@example.com
```

Sem `--password`, gera uma senha aleatória e imprime (guarde na hora — não
é mostrada de novo). Sempre imprime o **token de API**, necessário para
qualquer chamada em `/api/...` (ver seção de autenticação abaixo). O mesmo
usuário serve para o Django admin em `http://localhost:8000/admin/`.

## Popular uma instância de exemplo

Cria uma instância fictícia, credenciais de exemplo para os quatro
fornecedores e alguns produtos/variações ilustrando os formatos reais
vistos em `samples/` (nenhum é dado real de fornecedor):

```bash
docker compose exec backend python manage.py popular_instancia_exemplo
```

## Importar um fornecedor de verdade

Antes de importar, crie a instância (se ainda não existir) e uma
`CredencialFornecedor` ativa para o fornecedor desejado — via admin ou
shell. Depois:

```bash
docker compose exec backend python manage.py importar_fornecedor <slug-da-instancia> xbz
docker compose exec backend python manage.py importar_fornecedor <slug-da-instancia> asia
docker compose exec backend python manage.py importar_fornecedor <slug-da-instancia> somarcas
docker compose exec backend python manage.py importar_fornecedor <slug-da-instancia> spot
```

Busca o catálogo do fornecedor, normaliza para a forma canônica
(Produto + Variacao) e grava no espelho, criando uma `Execucao` com os
totais e um `LogItem` para cada erro. É idempotente: rodar de novo só
grava o que mudou (comparando `hash_conteudo`) e nunca duplica produto ou
variação.

A xbz tem limite de 24 chamadas/dia compartilhado com o cliente final — o
comando bloqueia uma segunda chamada no mesmo dia para a mesma instância a
menos que `--force` seja passado.

## Autenticação da API

Toda a API (`/api/instancias/...`) exige o header:

```
Authorization: Token <token do criar_admin_api>
```

A única exceção é `/api/tiny/oauth/callback/<slug>/` — continua pública de
propósito, porque quem chama é o navegador redirecionado pelo Tiny, sem
nenhum token nosso; a proteção real dela é o `state` (ver mais abaixo).

## Conectar uma instância ao Tiny (OAuth2)

1. `POST /api/instancias/` com `nome`, `client_id` e `client_secret` (gerados pelo
   cliente no módulo de Aplicativos do Tiny dele).
2. `GET /api/instancias/<slug>/` para pegar `url_callback` — cadastre essa URL,
   **idêntica**, como redirect URI no aplicativo do Tiny.
3. `GET /api/instancias/<slug>/autorizar/` devolve `url_autorizacao`: abra essa
   URL num navegador logado na conta do Tiny do cliente.
4. O Tiny redireciona para `GET /api/tiny/oauth/callback/<slug>/?code=...&state=...`,
   que troca o code por tokens e marca a instância como `conectado`.
5. `POST /api/instancias/<slug>/desconectar/` limpa os tokens e volta para
   `nao_conectado` (o slug continua travado — ver regra abaixo).

Nenhum endpoint devolve `client_secret`, `access_token` ou `refresh_token` —
só indicadores (`access_token_preenchido`, `token_expira_em`, `status` etc.).

### Renovação automática (agendada via Celery Beat)

O serviço `beat` do `docker-compose.yml` já dispara
`renovar_tokens_tiny` a cada 10 minutos, via worker (`docker compose up`
sobe tudo). Para rodar manualmente:

```bash
docker compose exec backend python manage.py renovar_tokens_tiny
```

Varre as instâncias `conectado` e renova proativamente o access_token das
que já passaram de 70% do tempo de vida — nunca espera dar 401. Falha na
renovação incrementa `tentativas_falha`; na 3ª falha seguida o status vira
`erro` e o comando para de tentar (só varre `conectado`) até alguém
reautorizar manualmente. Se o `refresh_token` já estiver expirado, nem
tenta renovar — marca direto para reautorização.

## Sincronização automática de fornecedores (cadência configurável)

Cada `CredencialFornecedor` ganha automaticamente uma `CadenciaFornecedor`
(60 minutos por padrão) — edite `intervalo_minutos` no admin por
instância+fornecedor. Um tick do Beat, a cada 5 minutos, dispara
`importar_fornecedor` para quem já venceu a cadência configurada. A xbz
recusa (`ValidationError`) qualquer cadência menor que 60 minutos —
proteção contra o limite de 24 chamadas/dia; os demais fornecedores podem
ser configurados para qualquer intervalo.

## Cadastrar produtos no Tiny

```bash
docker compose exec backend python manage.py cadastrar_produtos_tiny <slug-da-instancia>
```

Antes de rodar, configure `tiny_origem_padrao` e `tiny_unidade_medida_padrao`
na instância (admin) — o comando recusa rodar sem isso, e não existe valor
padrão fixo no código. Pega as `Variacao` com status `pendente`, verifica
se o SKU já existe no Tiny (nunca duplica um produto cadastrado
manualmente) e, se não existir, cria um produto Simples por variação. Uma
falha vira `status=erro` com o motivo em `ultimo_erro` e não trava o lote.
Retomável por construção: cada variação processada sai de `pendente`, então
rodar de novo só pega o que restou. Use `--limite N` para processar em
lotes menores.

O contrato oficial (passo 6) só exige `sku`, `descricao` e `tipo` — todo o
resto, incluindo NCM, é opcional. Uma variação sem NCM é cadastrada
normalmente; o comando só registra um aviso no log e soma no resumo final
("N variação(ões) sem NCM — pendência fiscal"), sem bloquear nem tratar
como erro. Na Spot isso hoje atinge ~4,5% dos SKUs (os que só têm código
CN/TARIC da UE); os demais já saem com NCM (ver `_ncm_do_taric`).

### Dimensões, imagens e outros campos opcionais enviados

O payload inclui `dimensoes` (largura/altura/comprimento/diâmetro em
**centímetros**, peso líquido/bruto em **quilogramas** — convenção da
própria tela de cadastro do Tiny, não documentada na API) quando o
fornecedor informa algo de forma confiável:

| Fornecedor | Dimensões | Peso |
|---|---|---|
| xbz | Altura/Largura/Profundidade→comprimento, já em cm | Peso em gramas ÷1000 |
| asia | altura/largura/comprimento, já em cm | peso, já em kg |
| Só Marcas | só `dimensoes_da_embalagem` ("AxLxP mm", rotulado) ÷10 → peso **bruto** | `peso_da_embalagem` ("N g") ÷1000 → peso **bruto** |
| Spot | só o padrão "ø\<N\> x \<N\> mm" de `CombinedSizes` (diâmetro+comprimento) ÷10 | não mapeado (ver pendências) |

Campos sem rotulação de eixo confiável (`dimensoes_do_produto` da Só
Marcas; `CombinedSizes` sem "ø" da Spot) nunca são parseados — adivinhar
qual número é largura/altura/comprimento seria inventar estrutura que o
dado não afirma.

Imagens (`Variacao.imagens`, já absolutas para xbz/asia/Só Marcas) viram
`anexos: [{url, externo: true}]` — o Tiny só guarda o link, sem subir
arquivo. Limitado a **5 anexos por produto** (escolha nossa, não pedida
pelo cliente — dá pra ajustar em `MAX_ANEXOS_POR_PRODUTO`, em
`cadastrar_produtos_tiny.py`). A Spot só entra na lista quando
`ConfiguracaoFornecedor.url_base_imagens` for preenchido.

`garantia` é enviado quando o fornecedor entrega isso (hoje, só a Só
Marcas, via `atributos["garantia_do_produto"]`). `marca` e `observacoes`
não são mapeados: `marca` no Tiny é uma referência a um ID já cadastrado
lá (não um nome de marca em texto), e nenhum fornecedor entrega algo que
sirva como `observacoes` sem inventar conteúdo.

## Atualizar estoque no Tiny

```bash
docker compose exec backend python manage.py atualizar_estoque_tiny <slug-da-instancia>
```

Para as `Variacao` já `cadastrado`, reenvia ao Tiny (como lançamento de
Balanço — define o saldo absoluto) o estoque que mudou no espelho desde a
última sincronização. Mesmo tratamento de throttle e resiliência a erro do
comando de cadastro; uma falha não muda o status (o produto continua
cadastrado) e será tentada de novo na próxima rodada.

## Rodar os testes

```bash
docker compose exec backend python manage.py test
```

## Estrutura

```
backend/
  config/            settings, urls, wsgi, asgi, celery.py — tudo lido de variável de ambiente
  apps/
    instancias/      Instancia (conta do Tiny), CredencialFornecedor, OAuth2 (tiny_oauth.py),
                     cliente HTTP com rate limit compartilhado (tiny_client.py + tiny_throttle.py),
                     tasks do Celery, e a API DRF (autenticada por token)
    catalogo/        Produto, Variacao, e os comandos cadastrar_produtos_tiny / atualizar_estoque_tiny
    sincronizacao/    Execucao e LogItem
    fornecedores/    cliente + normalizador por fornecedor, ConfiguracaoFornecedor,
                     CadenciaFornecedor, o comando importar_fornecedor, e as tasks do Celery Beat
```

## Modelo de dados (visão geral)

```
Instancia (1) ──< CredencialFornecedor
Instancia (1) ──< Produto ──< Variacao
Instancia (1) ──< Execucao ──< LogItem >── Variacao (opcional, SET_NULL)
```

Detalhes e diagrama completo no retorno da conversa que gerou este passo
(campos, índices e constraints de cada tabela).

## Regras de negócio do cliente, já cobertas por teste

1. **Cada cor/tamanho é uma Variacao própria**, que vira um produto
   separado no Tiny —
   `apps/catalogo/tests/test_regras_negocio.py::RegraCadaVariacaoViraProdutoProprioTests`.
2. **XBZ, `codigo_pai` iniciado por `"P@"` → descontinuado permanente**,
   nunca cadastrar — `Produto.esta_saindo_de_linha()` /
   `RegraXbzPrefixoSaindoDeLinhaTests`. É filtro de **prefixo**, não "contém
   `@` em qualquer posição" (isso muda a contagem de ~876 para 661 na
   amostra real).
3. **Estoque zero → status `aguardando`** (não cadastra, mas fica
   rastreado; reverte quando repõe estoque; nunca reabre um `descontinuado`
   nem um já `cadastrado`) — `Variacao.aplicar_regra_de_estoque()` /
   `RegraEstoqueZeroFicaAguardandoTests`.
4. **Preço gravado é sempre o do fornecedor, sem margem** —
   `Variacao.preco_venda_tiny` / `RegraPrecoSemMargemTests`.
5. **Slug imutável a partir do 1º access_token, não da mudança de status** —
   `Instancia.ja_foi_autorizada` (marcador permanente, sobrevive a um
   desconectar) / `apps/instancias/tests/test_models.py::InstanciaSlugTests`.
   Corrige uma suposição feita no passo 2.
6. **Renovação proativa a 70% do tempo de vida, 3 falhas seguidas → erro,
   refresh expirado → reautorização direta, sem tentar renovar** —
   `Instancia.precisa_renovar_token()` / `registrar_falha_renovacao()` /
   `marcar_para_reautorizacao()`, testados em
   `apps/instancias/tests/test_renovar_tokens_tiny.py`.
7. **xbz nunca sincroniza mais que 1x/hora** —
   `CadenciaFornecedor.CADENCIA_MINIMA_XBZ_MINUTOS` /
   `apps/fornecedores/tests/test_cadencia.py`.
8. **SKU já cadastrado no Tiny nunca é duplicado; falha nunca derruba o
   lote; cadastro é retomável** —
   `apps/catalogo/tests/test_cadastrar_produtos_tiny.py`.
9. **Preço da Só Marcas confirmado pelo cliente em 2026-09-04**: com
   gravação, com impostos — `apps/fornecedores/somarcas.py`.
10. **NCM não bloqueia mais o cadastro** (contrato oficial: só
    sku/descricao/tipo são obrigatórios) — vira aviso, nunca erro —
    `apps/catalogo/tests/test_cadastrar_produtos_tiny.py::NcmOpcionalTests`.
11. **Conversão de unidades de dimensão/peso por fornecedor** (cm/kg,
    convenção do Tiny) — um teste de conversão por fornecedor em
    `apps/fornecedores/tests/test_{xbz,asia,somarcas,spot}.py`.

## Pendências conhecidas (deixadas preparadas, não implementadas)

- **Spot / imagens**: vêm só como nome de arquivo, sem URL base
  (`apps/fornecedores/spot.py`). Existe `ConfiguracaoFornecedor.url_base_imagens`
  (registrada no admin), mas está vazia — enquanto isso, o normalizador da
  Spot não monta nenhuma URL de imagem.
- **Spot / campo fiscal**: o único campo fiscal da Spot é `Taric`. A
  amostra real (3.709 SKUs) mostra que ~95,5% trazem nele um código de 8
  dígitos (formato de NCM, só muda a pontuação) e ~4,5% trazem código
  CN10/TARIC da UE de 9-10 dígitos. `_ncm_do_taric` (`apps/fornecedores/spot.py`)
  aproveita só os de 8 dígitos para `Variacao.ncm` e **nunca trunca** os
  demais; o `Taric` cru fica sempre em `atributos["taric"]`. Registros Spot
  antigos: `python manage.py backfill_ncm_spot` (só toca `ncm`).
- ~~**Só Marcas / preço**~~ **Resolvido no passo 5**: a API devolve 4
  combinações de preço (com/sem gravação × com/sem impostos). O cliente
  confirmou em 2026-09-04 que o correto é `preco_com_gravacao_com_impostos`
  — o passo 3 tinha assumido `preco_sem_gravacao_sem_impostos` por engano.
- **Só Marcas / agrupamento**: confirmado contra a amostra real que não
  existe produto-pai — cada `codigo` já é uma variação de cor, sem chave de
  agrupamento estruturada (`produtos_similares` é texto livre, não uma FK).
- **Endpoint de autorização do Tiny (`TINY_OAUTH_AUTHORIZE_URL`)**: a
  especificação só deu o endpoint de *token*. O de autorização foi
  inferido do padrão do próprio Keycloak (mesmo realm, troca `token` por
  `auth`) — o endpoint de token real confirmou o resto do padrão (testei
  contra o Keycloak real do Tiny, que respondeu corretamente rejeitando
  credenciais falsas), mas o de `/auth` especificamente não foi exercitado
  de ponta a ponta. Configurável por env, sem precisar mudar código se
  estiver errado.
- ~~**`TINY_API_BASE_URL`**~~ **Corrigido no passo 6**: o passo 5 tinha
  usado `erp.tiny.com.br` por instrução explícita da época. O contrato
  oficial (https://api-docs.erp.olist.com/api-reference/produtos/criar-produto.md)
  declara `servers: https://api.tiny.com.br/public-api/v3` — é essa a URL
  em uso agora.
- ~~**NCM da Spot**~~ **Muda de figura no passo 6**: o contrato oficial
  confirma que NCM não é obrigatório — a Spot é cadastrada normalmente sem
  ele. O comando só registra um aviso (log + contagem no resumo), não
  bloqueia mais nada. Continua sendo uma pendência *fiscal* a resolver com
  o fornecedor, só não é mais uma pendência *técnica* que trava o cadastro.
- **`tiny_origem_padrao` ganhou validação de faixa (0–8) no passo 6**, mas
  já era `PositiveSmallIntegerField` desde o passo 5 — a instrução do
  passo 6 partia da premissa de que o campo era texto, o que não
  correspondia ao código; sinalizado nessa hora, sem "corrigir" um bug que
  não existia.
- **Preço-base do lançamento de estoque**: `atualizar_estoque` manda
  `precoUnitario` (campo obrigatório do endpoint de Balanço do Tiny) igual
  ao preço do fornecedor, sem margem — mesma regra do cadastro; não há
  outro preço "de custo" disponível para usar ali.
- **`Execucao`/`LogItem` não cobrem os comandos que escrevem no Tiny**:
  `cadastrar_produtos_tiny` e `atualizar_estoque_tiny` registram tudo em
  `Variacao.ultimo_erro` + saída do comando, mas não criam `Execucao` (que
  hoje só existe por fornecedor, não por "lote de cadastro no Tiny"). Se
  quiser o mesmo histórico consultável pelo admin, vale estender o modelo.
- **Throttle compartilhado tem uma race condition pequena e aceitável**: o
  lock por instância protege "verificar espaço e reservar vaga", mas dois
  processos podem, em teoria, disparar a requisição HTTP real quase ao
  mesmo tempo logo depois de reservar — o Redis garante que a CONTAGEM
  nunca ultrapassa o teto, mas não serializa as chamadas HTTP em si (e não
  precisa: o que protege a conta do cliente é a contagem, não a ordem).
