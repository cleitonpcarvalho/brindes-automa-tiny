# Deploy em produção

Stack: Docker Swarm + Traefik (rede externa `AutomaNet`, entrypoint
`websecure`, certresolver `letsencrypt`), imagens publicadas no GHCR,
deploy colando `stack.yml` no Portainer.

Domínios:
- `https://sync.automasoluct.com.br` → frontend
- `https://sync-api.automasoluct.com.br` → backend

## 1. Publicar as imagens

O workflow `.github/workflows/publish.yml` builda e publica a cada push em
`main`:

- `ghcr.io/cleitonpcarvalho/brindes-automa-tiny/backend:latest` (+ `:<sha curto>`)
- `ghcr.io/cleitonpcarvalho/brindes-automa-tiny/frontend:latest` (+ `:<sha curto>`)

Não precisa rodar nada manualmente — só fazer merge/push em `main`. Para
disparar sem um push novo, use "Run workflow" na aba Actions (o gatilho
`workflow_dispatch` está habilitado).

Os pacotes do GHCR são criados como privados por padrão. Na primeira
publicação, em github.com/cleitonpcarvalho/brindes-automa-tiny/pkgs → cada
pacote → Package settings, confirme que o pacote está linkado a este
repositório (Manage Actions access) para que o Portainer consiga fazer
`docker pull` — se a VPS não tiver credenciais do GHCR configuradas, ou
torne os pacotes públicos, ou configure um Registry no Portainer
(Registries > Add registry > GitHub Container Registry) com um Personal
Access Token com escopo `read:packages`.

## 1b. Deploy automático (stack já existente)

Depois que a stack já está criada no Swarm, o job `deploy` do mesmo
workflow (`.github/workflows/publish.yml`) atualiza os serviços sozinho a
cada push em `main`, **só se** o job `publish` (build+push das duas
imagens) terminar com sucesso.

O que ele faz, via SSH na VPS:

```
docker login ghcr.io            # token efêmero do próprio run (GITHUB_TOKEN)
docker service update --with-registry-auth --force --image <backend:latest>  brindes-automa-tiny_backend
docker service update --with-registry-auth --force --image <backend:latest>  brindes-automa-tiny_worker
docker service update --with-registry-auth --force --image <backend:latest>  brindes-automa-tiny_beat
docker service update --with-registry-auth --force --image <frontend:latest> brindes-automa-tiny_frontend
docker logout ghcr.io
```

Depois, o runner do GitHub confere `GET https://sync-api.automasoluct.com.br/health/`
(até ~5 min de tentativas) e falha o workflow se não voltar `200`.

**Por que `docker service update --force` e não `docker stack deploy`:** o
`--force` só troca a imagem e força o redeploy — o `command` de cada
serviço é preservado. Isso mantém o `--schedule=/tmp/celerybeat-schedule`
do `beat`. Um `docker stack deploy -c stack.yml` reaplicaria o `command`
do arquivo e, se o `stack.yml` estivesse desatualizado, quebraria o beat.
O `stack.yml` neste repo já inclui esse argumento no `beat`, mas o deploy
automático não depende disso.

Isso **não** cria a stack, não roda migrações e não mexe em
`postgres`/`redis`/`migrate`. Primeiro deploy e migrações continuam
manuais (seções 2 e 4).

### Secrets do GitHub necessários

Em *Settings → Secrets and variables → Actions*:

| Secret | Para que serve |
|---|---|
| `VPS_HOST` | IP ou hostname da VPS (ex.: `203.0.113.10`). |
| `VPS_USER` | Usuário SSH usado no deploy (precisa estar no grupo `docker` da VPS). |
| `VPS_SSH_KEY` | Chave **privada** SSH (conteúdo do arquivo, OpenPGP/OpenSSH), exclusiva do GitHub Actions. |
| `VPS_SSH_PORT` | Opcional. Porta SSH; se não cadastrar, usa `22`. |

Nenhum secret de GHCR é necessário — o job usa o `GITHUB_TOKEN` efêmero
(com permissão `packages: read`) para o `docker login` no nó do Swarm.

### Chave SSH exclusiva para o GitHub Actions

Sim — gere um par dedicado, não reaproveite sua chave pessoal:

```
# na sua máquina
ssh-keygen -t ed25519 -C "github-actions-deploy brindes-automa-tiny" -f ./gha_deploy -N ""
```

1. Copie a **pública** (`gha_deploy.pub`) para o usuário de deploy na VPS:
   `ssh-copy-id -i ./gha_deploy.pub deployuser@VPS_HOST`
   (ou cole a linha em `~deployuser/.ssh/authorized_keys`).
2. Cole a **privada** (`gha_deploy`, arquivo inteiro incluindo as linhas
   `-----BEGIN/END-----`) no secret `VPS_SSH_KEY`.
3. Apague `gha_deploy`/`gha_deploy.pub` da sua máquina depois.
4. O usuário de deploy precisa poder rodar `docker` sem `sudo` (estar no
   grupo `docker`) e ter acesso ao socket do Swarm manager.

Endurecimento opcional: restrinja a chave em `authorized_keys` com
`command="..."`/`from="<ip-do-runner>"`, ou fixe o host key da VPS no input
`fingerprint` da action.

## 2. Criar a stack no Portainer

1. Stacks → Add stack → Web editor.
2. Cole o conteúdo de `deploy/stack.yml`.
3. Preencha a seção "Environment variables" (ver lista abaixo) — são os
   únicos valores sensíveis; nada disso fica escrito no arquivo.
4. Deploy the stack.

Confira antes que a rede `AutomaNet` já existe no servidor (`docker network
ls`) — o stack a referencia como externa e não a cria.

## 3. Variáveis a preencher no Portainer

| Variável | O que é |
|---|---|
| `DJANGO_SECRET_KEY` | Chave interna do Django (assinatura de sessão, tokens do admin). Gere com: `python -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `FERNET_KEY` | Chave simétrica que cifra em repouso os tokens do Tiny e credenciais dos fornecedores. Gere com: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` — **guarde essa chave**; trocá-la depois de já existirem instâncias cadastradas torna irrecuperáveis os tokens/credenciais já salvos. |
| `POSTGRES_DB` | Nome do banco. Qualquer valor, ex.: `brindes_automa`. |
| `POSTGRES_USER` | Usuário do Postgres desta stack. Ex.: `brindes_automa`. |
| `POSTGRES_PASSWORD` | Senha do Postgres. Gere algo forte, ex.: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

Todo o resto (domínios, `DEBUG=False`, hosts, URLs internas, quantidade de
workers do Gunicorn) já está no `stack.yml` porque não é segredo — se
algum desses precisar mudar, edite o arquivo diretamente antes de colar.

## 4. Rodar as migrações e criar o primeiro usuário

Ver decisão detalhada na seção "Migrações" mais abaixo. Resumo prático:

1. Na stack já no ar, vá em Services → `<nome-da-stack>_migrate`.
2. Edite o serviço e mude "Replicas" de `0` para `1` → Update. O container
   sobe, roda `python manage.py migrate --noinput` e termina (exit 0) —
   ele não fica de pé, então não tem problema deixá-lo com replicas: 1
   depois; mas o padrão é devolver para `0` para não confundir o painel.
3. Confira o log do serviço (deve terminar com "Applying ... OK" ou "No
   migrations to apply").
4. Volte "Replicas" para `0`.
5. Abra o Console de um container do serviço `backend` (Containers →
   container do backend → Console → `/bin/sh`) e rode:

   ```
   python manage.py criar_admin_api --email seu@email.com --nome "Seu Nome"
   ```

   O comando já existe no projeto (`apps/instancias/management/commands/criar_admin_api.py`)
   e imprime, no final, o e-mail, a senha gerada (se você não passar
   `--password`) e o token de API — guarde os dois, a senha não é mostrada
   de novo. Rodar de novo com o mesmo `--email` não recria o usuário nem
   muda a senha, só reimprime o token.

Alternativa via CLI, se você tiver acesso SSH à VPS em vez de só o
Portainer:

```
docker service scale <nome-da-stack>_migrate=1
# espere o log do serviço terminar, depois:
docker service scale <nome-da-stack>_migrate=0
docker exec -it $(docker ps -q -f name=<nome-da-stack>_backend) \
  python manage.py criar_admin_api --email seu@email.com --nome "Seu Nome"
```

## 5. Verificar se subiu

- `curl -i https://sync-api.automasoluct.com.br/health/` → `200` com
  `{"status": "ok", "checks": {"database": true, "redis": true}}`. Se vier
  `503`, o campo `checks` diz qual dependência falhou.
- `https://sync.automasoluct.com.br/login` deve carregar a tela de login.
- Entre com o usuário criado no passo 4.
- No Portainer, Services: `backend`, `frontend`, `worker`, `beat`,
  `postgres`, `redis` devem estar todos com réplicas `1/1` e `migrate` com
  `0/0`.
- No dashboard do Traefik, os routers `sync-api` e `sync` devem aparecer
  como "up" com o certificado emitido pelo `letsencrypt`.

---

## Migrações — decisão tomada

Swarm não tem um recurso nativo de "rodar uma vez e sair" (ao contrário do
Job do Kubernetes) — um serviço normal, se rodar `migrate` no comando
principal, é reiniciado pelo `restart_policy` sempre que o processo
termina (migrate termina com sucesso rápido, então ele ficaria em loop de
restart). E colocar `migrate` no entrypoint do `backend`/`worker`/`beat`
faz os três competirem para migrar ao mesmo tempo no primeiro deploy (ou
em qualquer redeploy simultâneo) — exatamente o que foi pedido para
evitar.

A solução: um serviço `migrate` próprio, reaproveitando a imagem do
backend, com `deploy.replicas: 0` (não roda sozinho, nunca automaticamente)
e `restart_policy.condition: none` (quando ele sobe e termina, o Swarm não
tenta recriá-lo). Rodar a migração vira uma ação explícita e única —
escalar para `1` réplica, esperar terminar, escalar de volta para `0` —
nunca concorrente com os outros serviços subindo.

## Decisões tomadas sem instrução explícita

- **Rede interna própria (`interna`), além da `AutomaNet` externa.**
  `postgres`/`redis` só entram na rede interna — nunca ficam alcançáveis
  por outras stacks que também usam `AutomaNet`, como pedido ("não
  compartilhados"). `backend`/`frontend` entram nas duas: `AutomaNet` para
  o Traefik rotear, `interna` para falar com banco/Redis/entre si. Também
  evita colisão de nome: como o Next.js chama o backend pelo nome curto
  `http://backend:8000`, se ambos estivessem só na `AutomaNet` (compartilhada
  com outras stacks do servidor), um serviço `backend` de outra stack
  poderia colidir com esse alias.
- **Nomes dos routers Traefik são `sync-api`/`sync`**, não `backend`/
  `frontend` — nomes de router precisam ser únicos em todo o Traefik
  (compartilhado entre stacks do servidor), então usei o nome do próprio
  subdomínio para não colidir com outra stack que já tenha um serviço
  chamado "backend".
- **WhiteNoise para servir estáticos.** Gunicorn/WSGI não serve arquivos
  estáticos sozinho, e o Traefik só roteia — não há nginx nem outro
  servidor de estáticos nesta stack. Sem isso, `/admin/` sobe sem CSS/JS.
  Adicionei `whitenoise` como dependência e `STATIC_ROOT` +
  `WhiteNoiseMiddleware` no `settings.py`; o `collectstatic` já roda no
  build da imagem (Parte 1 pedia isso explicitamente).
- **`SECURE_PROXY_SSL_HEADER` e `CSRF_TRUSTED_ORIGINS`.** Atrás do Traefik
  (que termina o TLS), sem isso o Django vê a requisição como HTTP puro e
  rejeita POSTs do `/admin/` com "CSRF verification failed" — é um dos
  itens da seção "o que pode falhar" abaixo, então preferi já corrigir no
  `settings.py` em vez de só documentar o sintoma.
- **`CORS_ALLOWED_ORIGINS` continua sendo só uma variável de ambiente.**
  Não criei middleware novo: o `django-cors-headers` já está instalado e
  configurado (passo 7); só faltava apontar a origem certa em produção,
  que é o que o `stack.yml` faz. Vale notar que, na prática, o navegador
  nunca chama o backend direto — o cliente HTTP do frontend
  (`frontend/src/lib/api/client.ts`) fala com as próprias rotas do Next.js
  (`/api/backend/*`), que proxeiam para o Django *dentro* da rede Docker
  (`BACKEND_INTERNAL_URL`). CORS entra em jogo só se algo no navegador
  chamar `sync-api.automasoluct.com.br` diretamente (ex.: acessar o
  `/admin/` pelo domínio da API) — mantive a origem configurada mesmo
  assim, por ser barato e correto.
- **`GUNICORN_WORKERS=2`** como padrão para a VPS modesta — ajustável só
  editando `stack.yml`, sem rebuild de imagem (o Dockerfile lê a variável
  em runtime).
- **Postgres e Redis com `-alpine`** (`postgres:16-alpine`, já era
  `redis:7-alpine` no compose de dev) para reduzir a imagem baixada numa
  VPS modesta.
- **Tag `:latest` no `stack.yml`**, não o SHA. O workflow publica os dois,
  mas fixar `:latest` deixa o fluxo do Portainer mais simples (paste do
  arquivo e "re-pull image" força reimplantar a versão mais nova). Se
  quiser reprodutibilidade/rollback por SHA, troque manualmente a tag no
  `stack.yml` antes de colar — é só editar a imagem de `backend`/`frontend`
  (e do `worker`/`beat`/`migrate`, que reaproveitam a mesma âncora
  `*backend-image`).
- **Sem healthcheck HTTP dedicado no frontend** (não foi pedido) — usei um
  `wget --spider` na home, que basta para detectar "processo Node não
  responde".

## O que pode falhar no primeiro deploy, e como diagnosticar

- **`backend`/`worker`/`beat` em crash-loop antes de rodar a migração.**
  Esperado: sem as tabelas do Django, qualquer request que toque o banco
  falha. Depois de rodar `migrate` (Parte 4), eles devem estabilizar
  sozinhos (restart_policy: any já cobre isso). Se continuar reiniciando
  depois da migração, veja o log do container.
- **`/health/` responde 503 com `"redis": false`.** Confira se `redis` e
  `backend` estão na mesma rede (`interna`) e se `REDIS_URL` bate com
  `redis://redis:6379` (nome do serviço, não `localhost`).
- **`/health/` responde 503 com `"database": false`, ou o backend nem sobe.**
  Confira se as variáveis `POSTGRES_DB`/`POSTGRES_USER`/`POSTGRES_PASSWORD`
  preenchidas no Portainer são **exatamente** as mesmas usadas pelo
  container `postgres` (são a mesma variável reaproveitada nos dois
  lugares no `stack.yml`, então isso só desalinha se você editar um dos
  dois lados à mão).
- **Certificado não emite / Traefik não descobre o serviço.** Confirme que
  o label `traefik.docker.network=AutomaNet` bate com o nome real da rede
  no servidor (`docker network ls`) e que o DNS do Cloudflare já resolve
  para o IP da VPS (sem isso o `letsencrypt` HTTP-01 challenge falha).
- **Login no admin (`/admin/`) falha com "CSRF verification failed".**
  Sintoma clássico de reverse proxy terminando TLS sem `SECURE_PROXY_SSL_HEADER`
  — já mitigado no `settings.py` (ver decisões acima), mas se ainda
  acontecer, confira se o Traefik está mandando o header
  `X-Forwarded-Proto: https` (comportamento padrão dele, mas pode ter sido
  desabilitado nas outras stacks do servidor).
- **`worker`/`beat` sobem mas nada é sincronizado.** Confira se o
  `CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` (derivados de `REDIS_URL` no
  `settings.py`) apontam pro Redis certo — mesmo ponto do item acima.
- **Pull da imagem falha no Portainer ("unauthorized"/"not found").**
  Pacote do GHCR ainda privado sem credencial configurada — ver nota no
  fim da Parte 1.
- **`beat` "esquece" o último agendamento após um restart.** O
  `celerybeat-schedule` (arquivo local do scheduler) não tem volume
  persistente nesta stack — de propósito, para não somar mais um volume
  por uma bobagem: as tasks agendadas (`renovar_tokens_tiny_task`,
  `verificar_e_disparar_sincronizacoes`) decidem o que fazer consultando o
  banco, não o arquivo de schedule, então na pior hipótese um restart do
  `beat` pode causar um tick extra perto do horário de sempre — sem
  efeito colateral real dado como as tasks são escritas hoje.
