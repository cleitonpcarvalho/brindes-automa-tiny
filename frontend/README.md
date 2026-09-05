# frontend/

Frontend Next.js do brindes-automa-tiny. Passo 7: fundação, design system
e fluxo de autenticação. Passo 8: dashboard e listagem de instâncias de
verdade. **O detalhe de uma instância (produtos, execuções, credenciais
por fornecedor) é só um placeholder por enquanto — vem no passo 9.**

## Stack

Next.js 15 (App Router), TypeScript estrito, Tailwind CSS v4, shadcn/ui
(base Radix), TanStack Query, Vitest + Testing Library, Docker.

## Subir o ambiente

Pela raiz do projeto (sobe tudo: Postgres, Redis, backend, worker, beat e
frontend):

```bash
docker compose up --build
```

Frontend em `http://localhost:3000`, backend em `http://localhost:8000`.
Crie um usuário antes de logar (ver `backend/README.md`):

```bash
docker compose exec backend python manage.py criar_admin_api --email seu-email@exemplo.com
```

Login é por e-mail de verdade (passo 8): o modelo de usuário
(`apps.contas.Usuario`, backend) tem e-mail único como identificador de
autenticação — não é mais um `username` com formato de e-mail.

## Rodar fora do Docker (opcional)

```bash
cd frontend
npm install
BACKEND_INTERNAL_URL=http://localhost:8000 npm run dev
```

Precisa do backend já rodando (`docker compose up backend db`) e de
`CORS_ALLOWED_ORIGINS=http://localhost:3000` no `.env` da raiz (já é o
padrão).

## Testes

```bash
npm run test
```

Vitest + Testing Library. Cobrem a renderização da listagem de instâncias
(cada status, estados de carregamento/erro/vazio) e o painel de alertas do
dashboard (incluindo a lista vazia) — ver `*.test.tsx` ao lado dos
componentes em `components/instancias/` e `components/dashboard/`.

## Gerar os tipos da API

```bash
npm run generate:types
```

Regenera `src/lib/api/schema.ts` a partir do schema OpenAPI real do
backend (`http://localhost:8000/api/schema/`, via `drf-spectacular`).
Rode de novo sempre que um endpoint mudar no backend — nunca edite
`schema.ts` à mão.

## Como a sessão é guardada

O token do DRF fica num **cookie httpOnly**, gravado pelo servidor
Next.js (não pelo navegador) logo depois do login. Página nenhuma nem
JavaScript do navegador consegue ler esse valor — isso corta o vetor mais
comum de roubo de token (XSS): mesmo que um script malicioso rode na
página, ele não tem como ler `document.cookie` e exfiltrar a sessão.

Como o navegador não pode ler o cookie, ele também não pode montar o
header `Authorization` sozinho. Por isso todo dado passa por um **proxy**
dentro do próprio Next.js (`app/api/backend/[...path]/route.ts`): o
navegador chama `/api/backend/...` (mesma origem, sem CORS), o servidor
Next.js lê o cookie e só aí anexa `Authorization: Token <token>` antes de
repassar pro Django. O navegador nunca vê o token, nem em memória JS.

- `/api/auth/login` — troca usuário/senha pelo token no Django e grava o cookie.
- `/api/auth/logout` — apaga o token no Django e remove o cookie.
- `/api/backend/[...path]` — proxy autenticado para todo o resto da API.
- `middleware.ts` — barra rota protegida sem o cookie presente (redireciona pro login).

"Manter conectado" desmarcado expira a sessão em 1 dia; marcado, em 30 dias.

Um 401/403 vindo do proxy (token revogado/expirado) é tratado no cliente
de API (`lib/api/client.ts`): desconecta e manda de volta pro login na
hora, de qualquer tela.

## Estrutura

```
frontend/
  src/
    app/
      login/                 tela de login (pública)
      (app)/                 grupo de rotas autenticadas — layout = AppShell
        dashboard/           visão geral: cards, alertas, atividade recente (passo 8)
        instancias/          listagem com busca/filtro/paginação (passo 8)
        instancias/[slug]/   detalhe da instância — placeholder (conteúdo real no passo 9)
      api/
        auth/login/          troca credenciais por token, grava cookie httpOnly
        auth/logout/         apaga token e cookie
        backend/[...path]/   proxy autenticado pro Django
      globals.css            tema (tokens extraídos de design/02-dashboard/DESIGN.md)
    components/
      ui/                    primitivos shadcn (Button, Input, Select, Checkbox,
                              Switch, Card, Badge, StatusDot, Table, Tabs, Skeleton,
                              DropdownMenu, EmptyState/ErrorState...)
      shell/                 Sidebar, AppShell, contexto de colapso
      auth/                  formulário de login
      dashboard/             cards de métrica, painel de alertas, atividade recente
      instancias/            toolbar, tabela, pills de fornecedor, menu de ações
      providers/             QueryClientProvider
    lib/
      api/                   schema.ts (gerado), types.ts, client.ts, hooks.ts
      auth/                  helpers de sessão (nome do cookie, URL do backend)
      format.ts               números, tempo relativo e duração
    middleware.ts            proteção de rotas
```

## Tema (design/02-dashboard/DESIGN.md)

Dark-only — a classe `dark` é sempre aplicada no `<html>`, não depende da
preferência do sistema. Cores, tipografia, espaçamento e raio vêm dos
tokens definidos em `src/app/globals.css`, nunca escritos direto no JSX.
Ver o retorno da conversa (passo 7) para a lista completa de tokens e as
divergências encontradas entre o front-matter YAML do DESIGN.md (não
usado) e o HTML de referência (usado).

## Qualidade

- TypeScript `strict`, `@typescript-eslint/no-explicit-any` como erro (não warning).
- `npm run lint` e `npm run build` rodam type-check + lint — os dois têm que passar sem avisos antes de commitar.
- Números sempre com `tabular-nums` (embutido nas utilities `text-mono-metric*` e nas células de tabela).
