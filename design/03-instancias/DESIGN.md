---
name: Precision Engineering Interface
colors:
  surface: '#121315'
  surface-dim: '#121315'
  surface-bright: '#38393b'
  surface-container-lowest: '#0d0e10'
  surface-container-low: '#1b1c1e'
  surface-container: '#1f2022'
  surface-container-high: '#292a2c'
  surface-container-highest: '#343537'
  on-surface: '#e3e2e5'
  on-surface-variant: '#c2c6d7'
  inverse-surface: '#e3e2e5'
  inverse-on-surface: '#303033'
  outline: '#8c90a0'
  outline-variant: '#424654'
  surface-tint: '#b2c5ff'
  primary: '#b2c5ff'
  on-primary: '#002c72'
  primary-container: '#105edd'
  on-primary-container: '#dee4ff'
  inverse-primary: '#0056d1'
  secondary: '#4ae176'
  on-secondary: '#003915'
  secondary-container: '#00b954'
  on-secondary-container: '#004119'
  tertiary: '#ffb95f'
  on-tertiary: '#472a00'
  tertiary-container: '#905b00'
  on-tertiary-container: '#ffe1c0'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dae2ff'
  primary-fixed-dim: '#b2c5ff'
  on-primary-fixed: '#001847'
  on-primary-fixed-variant: '#0040a0'
  secondary-fixed: '#6bff8f'
  secondary-fixed-dim: '#4ae176'
  on-secondary-fixed: '#002109'
  on-secondary-fixed-variant: '#005321'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#121315'
  on-background: '#e3e2e5'
  surface-variant: '#343537'
typography:
  title-page:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  title-page-mobile:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.015em
  header-section:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: -0.01em
  body-default:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-medium:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: -0.005em
  caption-label:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  caption-medium:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.005em
  mono-metric:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0em
  mono-metric-lg:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.02em
  code-inline:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  grid-base: 8px
  space-xxs: 2px
  space-xs: 4px
  space-sm: 8px
  space-md: 12px
  space-lg: 16px
  space-xl: 20px
  space-2xl: 24px
  space-3xl: 32px
  section-gap: 24px
  card-padding: 16px
  input-height: 32px
  button-height: 32px
---

## Brand & Style

Este design system foi concebido como um instrumento de precisão cirúrgica para automação avançada, monitoramento operacional e fluxos de trabalho de alta densidade técnica. Inspirado na sobriedade de dashboards contemporâneos de engenharia (Linear, Vercel), o ambiente visual prioriza foco estrito, ausência absoluta de ruído cosmético e legibilidade imediata de métricas críticas.

### Princípios Visuais
- **Instrumento Utilitário:** Cada pixel, borda e elemento tem função operacional comprovada. Sem gradientes decorativos, sem desfoques difusos desnecessários e sem ornamentações.
- **Calma sob Pressão:** A paleta near-black reduz o cansaço visual em salas de controle e turnos prolongados de desenvolvimento. O uso comedido de acentos direciona a atenção apenas quando há tomada de ação requerida.
- **Contraste Estrutural Nítido:** Separação entre módulos através de micro-linhas e transições tonais sólidas, garantindo limites claros entre métricas, logs e controles interativos.

## Colors

A paleta de cores atua sob o modelo de contenção rigorosa: superfícies escuras profundas sustentam informações analíticas onde as cores semânticas possuem significado funcional direto e inegociável.

### Superfícies e Estrutura
- **Base Canvas (`#0B0C0E`):** Plano de fundo fundamental para telas e matrizes operacionais.
- **Superfície Elevada (`#141619`):** Superfície de cartões, painéis modulares, menus laterais e inspetores.
- **Superfície Interativa / Hover (`#1C1F24`):** Realce sutil para linhas de tabelas interativas e estados hover secundários.
- **Borda Estrutural Padrão (`#23262B`):** Delimitação precisa de 1px entre componentes e seções.
- **Borda Sutil / Separador Interno (`#1A1D21`):** Divisores horizontais de tabelas e listas secundárias.

### Acentos e Ações
- **Primary Electric Blue (`#105EDD`):** Reservado com disciplina para CTAs primários, estados de navegação ativos, anéis de foco do teclado e indicadores de métricas vitais selecionadas.
- **Primary Hover (`#0D4DB5`):** Feedback interativo para gatilhos primários.
- **Primary Muted / Tint (`#105EDD1F`):** Fundo translúcido para badges ativas e seleções de células de grid.

### Estados e Diagnóstico
- **Success / Connected (`#22C55E`):** Nós ativos, conexões operacionais e automações saudáveis. Subtom de superfície: `#22C55E1A`.
- **Warning / Action Needed (`#F59E0B`):** Fila represada, instabilidade momentânea ou autorização pendente. Subtom de superfície: `#F59E0B1A`.
- **Error / Expired (`#EF4444`):** Interrupção de automação, tokens invalidados e falhas de runtime. Subtom de superfície: `#EF44441A`.
- **Neutral Slate / Idle (`#94A3B8`):** Rótulos, metadados, timestamps, dados inativos e texto secundário.
- **Texto Principal (`#F8FAFC`):** Leitura de títulos, valores primários de métricas e inputs ativos.

## Typography

A tipografia é orientada pela clareza analítica e precisão dimensional. Utiliza-se a família **Inter** em toda a hierarquia textual, complementada pontualmente por **JetBrains Mono** para tokens brutos de código e payloads.

### Regras de Aplicação
- **Figuras Tabulares (`font-variant-numeric: tabular-nums` / `tnum`):** Obrigatório para todos os números, valores percentuais, relógios de execução, tempos de resposta (latência) e contadores. Evita trepidação na renderização contínua de dashboards em tempo real.
- **Rótulos e Metadados:** Tipografia em 12px aplicada com cor `#94A3B8`. Usada em chaves de pares chave-valor, cabeçalhos de coluna em tabelas e legendas técnicas.
- **Títulos e Subtítulos:** Título de página fixado em 24px semi-bold (`#F8FAFC`), seções em 15px medium (`#F8FAFC`), garantindo uma relação de escala densa e compacta, sem desperdício de espaço vertical.

## Layout & Spacing

O layout adota uma grade base estrita de 8px com micro-ajustes em subunidades de 4px para elementos compactos de dados. O ritmo horizontal e vertical prioriza a concentração controlada de informação legível.

### Grid e Distribuição
- **Estrutura de Tela:** Grid fluido contido entre 1280px e 1600px em monitores de alta resolução, adaptado para navegação lateral fixa (sidebar de 240px colapsável para 56px de ícones).
- **Ritmo entre Seções:** Espaçamento padronizado de exatamente 24px (`space-2xl`) entre módulos, cartões de agrupamento analítico e cabeçalhos de visualização.
- **Alinhamentos Internos:** Cartões de métricas operacionais utilizam padding interno de 16px. Modais e painéis de configuração densa utilizam 20px a 24px.

### Responsividade e Breakpoints
- **Desktop Primário (≥ 1280px):** Layout completo multi-coluna (3 a 4 colunas de métricas, grids de automação em 12 colunas fracionadas).
- **Tablet / Laptop Compacto (768px - 1279px):** Conversão automática para 2 colunas com barras laterais em gaveta retrátil (*drawer*). Margens laterais fixadas em 16px.
- **Mobile (< 768px):** Coluna única contínua. Elementos de tabela ganham suporte a scroll horizontal rígido ou conversão em listas de cartões verticais com labels explicitados.

## Elevation & Depth

Este design system não utiliza sombras difusas estéticas ou efeitos de profundidade artificial. A separação física e hierárquica é expressa por camadas tonais discretas e contornos milimétricos.

### Níveis de Superfície
1. **L0 (Plano de Fundo Operacional):** `#0B0C0E` — Área neutra sem interatividade direta.
2. **L1 (Painéis e Cartões Operacionais):** `#141619` com borda contínua de 1px em `#23262B`. Superfície padrão para toda interface de trabalho.
3. **L2 (Elementos Sobrepostos e Menus Suspensos):** `#1A1D21` com borda de 1px em `#2D3139`. Utilizado para dropdowns, menus de contexto, popovers e tooltips.
4. **L3 (Modais e Inspetores Críticos):** `#141619` com borda em `#2E333D` e sombra direcional utilitária restrita a overlays: `box-shadow: 0 16px 32px -8px rgba(0, 0, 0, 0.7)`.

### Iluminação e Estados de Foco
- Acessibilidade e seleção ativa por teclado são demarcadas estritamente com outline de 2px sólido em `#105EDD` e offset de 2px em `#0B0C0E`.
- Proibido o uso de *drop shadows* coloridas, brilhos neon (*glow effects*) ou texturas refletivas.

## Shapes

A linguagem formal comunica estabilidade e precisão através de cantos suavemente controlados, sem arredondamentos excessivos que desperdiçam área útil ou infantilizam a interface.

### Regras Geométricas
- **Cartões, Módulos e Tabelas:** Arredondamento fixo de exatamente `10px`. Proporciona uma contenção técnica moderna sem cair na suavidade de interfaces de consumo.
- **Botões, Entradas de Dados e Menus:** Arredondamento fixo de `8px`. Uniformiza o alinhamento visual de campos de formulário e ações dispostas lado a lado.
- **Badges, Tags e Status Pills:** Arredondamento contido de `4px` a `6px` para chips retangulares estruturados, ou `9999px` (pílula total) exclusivamente quando associado a indicadores circulares de status de 6px.
- **Ícones:** Linha fina vetorial (1.5px stroke), inscritos rigidamente dentro de uma caixa delimitadora de 16x16px.

## Components

Instruções formais para construção e manutenção dos elementos de interface.

### Botões (Buttons)
- **Primary:** Fundo `#105EDD`, texto `#FFFFFF`, borda transparente, altura 32px, padding horizontal 12px, font-weight 500, font-size 14px, radius 8px. Hover: `#0D4DB5`. Active: `#0A3D91`.
- **Secondary / Outline:** Fundo `#141619`, texto `#F8FAFC`, borda 1px `#23262B`, altura 32px, padding horizontal 12px. Hover: Fundo `#1C1F24`, borda `#2E333D`.
- **Ghost:** Fundo transparente, texto `#94A3B8`, sem borda. Hover: Fundo `#141619`, texto `#F8FAFC`.
- **Destructive:** Fundo `#EF44441A`, texto `#EF4444`, borda 1px `#EF44444D`. Hover: Fundo `#EF4444`, texto `#FFFFFF`.

### Campos de Entrada (Input Fields)
- Fundo `#0B0C0E`, borda 1px `#23262B`, altura 32px, padding horizontal 10px, texto `#F8FAFC`, font-size 14px, radius 8px.
- **Placeholder:** `#94A3B8` em opacidade 60%.
- **Focus:** Borda `#105EDD` com anel de foco `0 0 0 1px #105EDD`.
- **Disabled:** Fundo `#141619`, borda `#1A1D21`, texto `#94A3B8` opacidade 40%, cursor `not-allowed`.

### Badges de Status & Chips
- Estrutura base: Altura 22px, padding horizontal 6px, radius 4px, font-size 12px, font-weight 500.
- **Conectado / Sucesso:** Fundo `#22C55E1A`, texto `#22C55E`, borda 1px `#22C55E33`. Ponto indicador opcional: círculo preenchido de 6px em `#22C55E`.
- **Pendente / Alerta:** Fundo `#F59E0B1A`, texto `#F59E0B`, borda 1px `#F59E0B33`.
- **Erro / Expirado:** Fundo `#EF44441A`, texto `#EF4444`, borda 1px `#EF444433`.
- **Neutro / Ocioso:** Fundo `#1A1D21`, texto `#94A3B8`, borda 1px `#23262B`.

### Cartões Operacionais (Cards)
- Fundo `#141619`, borda 1px `#23262B`, radius 10px, padding 16px.
- **Header do Cartão:** Título em 15px medium (`#F8FAFC`), rótulo de apoio em 12px (`#94A3B8`). Divisor opcional com linha contínua de 1px em `#23262B`.

### Tabelas de Dados e Métricas
- **Linha de Cabeçalho:** Altura 32px, fundo `#0B0C0E`, texto 12px medium em `#94A3B8`, alinhamento vertical central, borda inferior 1px `#23262B`.
- **Linha de Dados:** Altura 40px, fundo `#141619`, texto 14px regular tabular (`tnum`) em `#F8FAFC`, borda inferior 1px `#1A1D21`. Hover na linha: fundo `#1C1F24`.

### Seletores e Controles (Checkboxes & Switches)
- **Checkbox:** Caixa de 16x16px, radius 4px, borda 1px `#23262B`, fundo `#0B0C0E`. Estado checked: fundo `#105EDD`, borda `#105EDD`, ícone de check 12px branco centralizado.
- **Switch:** Trilho de 32x18px, radius 9999px, fundo `#23262B`. Thumb de 14x14px branco com transição linear de 150ms. Estado checked: fundo do trilho em `#105EDD`.