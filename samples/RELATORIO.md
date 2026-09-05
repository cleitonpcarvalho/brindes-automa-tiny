# Relatório de amostras das APIs de fornecedores

Gerado por `tools/analyze_samples.py`. Não contém preços reais nem o JSON bruto —
apenas estrutura, tipos e percentuais de preenchimento.

## xbz

Arquivos analisados: produtos_2026-09-04_1413.json

**1. Produtos na amostra:** 11565

**2. Campos no nível do produto:**

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `Altura` | float | 100% | 0.0 |
| `CodigoAmigavel` | str | 100% | 06520 |
| `CodigoComposto` | str | 100% | 06520-AZU |
| `CodigoXbz` | str | 100% | X000019 |
| `CorWebPrincipal` | str | 100% | AZUL |
| `CorWebPrincipalId` | int | 100% | 1 |
| `CorWebSecundaria` | str | 99% | AZUL |
| `CorWebSecundariaId` | int | 100% | 1 |
| `Descricao` | str | 94% | Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e detal… |
| `IdPessoa` | int | 100% | 0 |
| `IdProduto` | int | 100% | 1 |
| `IdStatusConfiabilidade` | int | 100% | 10 |
| `ImageLink` | str | 97% | https://cdn.xbzbrindes.com.br/img/produtos/3/6520-AZU-Caneca-400ml-Acrilica-249… |
| `Largura` | float | 100% | 0.0 |
| `Ncm` | str | 100% | 73239300 |
| `Nome` | str | 100% | CANECA ACRÍLICA 400 ML COM TAMPA |
| `Peso` | float | 100% | 154.0 |
| `PontaDeEstoque` | bool | 100% | False |
| `PrecoVenda` | float | 100% | (oculto: campo de preço) |
| `PrecoVendaFormatado` | str | 100% | (oculto: campo de preço) |
| `Profundidade` | float | 100% | 0.0 |
| `QuantidadeDisponivel` | int | 100% | 5690 |
| `QuantidadeDisponivelEstoquePrincipal` | int | 100% | 399 |
| `ReposicaoDataPrevista` | str | 100% | 2026-09-29T00:00:00 |
| `SiteLink` | str | 97% | http://www.xbzbrindes.com.br/06520 |
| `StatusConfiabilidade` | str | 100% | Quantidade CONFIÁVEL. Confirmada através de inventário realizado recentemente. |
| `WebSubTipo` | — | 0% | — |
| `WebSubTipoId` | int | 100% | 0 |
| `WebTipo` | str | 0% | PONTA DE ESTOQUE |
| `WebTipoId` | int | 100% | 0 |

**3. Campos aninhados:** nenhum campo de lista de objetos encontrado no nível do produto.

**4. Candidato a identificador único:**
   - `CodigoAmigavel`: 11565 preenchidos, 3658 valores distintos → NÃO único / incompleto na amostra
   - `CodigoComposto`: 11565 preenchidos, 11565 valores distintos → ÚNICO na amostra
   - `CodigoXbz`: 11565 preenchidos, 11565 valores distintos → ÚNICO na amostra
   - `IdPessoa`: 11565 preenchidos, 1 valores distintos → NÃO único / incompleto na amostra
   - `IdProduto`: 11565 preenchidos, 11565 valores distintos → ÚNICO na amostra
   - `IdStatusConfiabilidade`: 11565 preenchidos, 1 valores distintos → NÃO único / incompleto na amostra

**5. NCM:**
   - Presente no nível do produto: `Ncm`

**6. Imagens (URL absoluta vs. caminho relativo):**
   - `ImageLink`: URL absoluta

**7. Campo de data de atualização para sincronização incremental:**
   - Nenhum campo de data de atualização identificado no nível do produto.

**8. Produtos inativos/cancelados:**
   - Nenhum campo de status/ativo identificado; não foi possível determinar quantos produtos estão inativos.


## asia

Arquivos analisados: produtos_pagina1_2026-09-04_1410.json, produtos_pagina2_2026-09-04_1410.json, produtos_pagina3_2026-09-04_1410.json

**1. Produtos na amostra:** 300
   - Variações/itens em `propriedades2`: 2270 no total, presentes em 300 produtos
   - Variações/itens em `variacoes`: 985 no total, presentes em 300 produtos

**2. Campos no nível do produto:**

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `altura` | int/float | 100% | 45 |
| `categorias` | dict | 100% | {'277': 'Bolsas &amp; Mochilas Maternidade', '105': 'Mochilas', '186': 'Mochila… |
| `comprimento` | int/float | 100% | 39 |
| `descricao` | str | 100% | Bolsa multifuncional em poliéster 300D com detalhes em PU e interior em 210D. P… |
| `galeria` | list | 100% | ['https://media.asiaimport.com.br/2024/05/IMG_7218.jpg', 'https://media.asiaimp… |
| `imagem` | str | 100% | https://media.asiaimport.com.br/2024/05/Perfil_novo-30.jpg |
| `largura` | int/float | 100% | 38 |
| `nome` | str | 100% | Bolsa Multifuncional em Poliéster 300D |
| `origem_faturamento` | str | 100% | SC |
| `peso` | float/int | 100% | 0.868 |
| `preco` | str | 100% | (oculto: campo de preço) |
| `promocao` | int | 100% | 1 |
| `propriedades` | dict | 100% | {'dimensao-produto': '39x42x18cm (AxLxP)', 'peso-do-produto': '0,868kg', 'quant… |
| `propriedades2` | list | 100% | [{'name': 'Dimensão Produto', 'slug': 'dimensao-produto', 'value': '39x42x18cm … |
| `referencia` | str | 100% | MC511P |
| `status` | str | 100% | true |
| `tags` | dict/list | 100% | {'291': 'Ofertas', '161': 'Promoção'} |
| `variacoes` | list | 100% | [{'referencia': 'MC511', 'nome': 'Bolsa Multifuncional em Poliéster 300D', 'pre… |
| `video` | str | 93% | https://www.youtube.com/embed/CMwB3iYoV08 |

**3. Campos aninhados:**

_Nível `propriedades2`_

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `name` | str | 100% | Dimensão Produto |
| `slug` | str | 100% | dimensao-produto |
| `value` | str | 99% | 39x42x18cm (AxLxP) |

_Nível `variacoes`_

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `atributos` | dict | 100% | {'cor': {'name': 'cinza', 'value': 'Cinza', 'hexadecimal': '#7f7f7f'}, 'volume-… |
| `color_id` | str | 1% | OF |
| `imagem` | str | 100% | https://media.asiaimport.com.br/2024/05/IMG_7230.jpg |
| `ncm` | str | 100% | 4202.92.00 |
| `nome` | str | 100% | Bolsa Multifuncional em Poliéster 300D |
| `preco` | str | 100% | (oculto: campo de preço) |
| `previsao_entrega` | list | 100% | [] |
| `qtd_estoque` | int | 100% | 675 |
| `qtd_estoque_em_sp` | int | 100% | 0 |
| `referencia` | str | 100% | MC511 |

**4. Candidato a identificador único:**
   - `referencia`: 300 preenchidos, 300 valores distintos → ÚNICO na amostra

**5. NCM:**
   - Presente no nível `variacoes`: `ncm`

**6. Imagens (URL absoluta vs. caminho relativo):**
   - `galeria`: URL absoluta
   - `imagem`: URL absoluta

**7. Campo de data de atualização para sincronização incremental:**
   - Nenhum campo de data de atualização identificado no nível do produto.

**8. Produtos inativos/cancelados:**
   - `status`: distribuição de valores → 'true'=300


## somarcas

Arquivos analisados: produtos_2026-09-04_1632.json

**1. Produtos na amostra:** 1278

**2. Campos no nível do produto:**

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `codigo` | str | 100% | AS-00610 |
| `data_ultima_atualizacao` | str | 100% | 2026-09-04 11:51:45 |
| `descricao` | str | 100% | Garrafa em alumínio branco. Conta com tampa plástica rosqueável preta com alça.… |
| `dimensoes_da_embalagem` | str | 100% | 0x0x0 mm (AxLxP) |
| `dimensoes_do_produto` | str | 100% | 24,5x7cm |
| `embalagem_do_produto` | str | 100% | Caixa Preta |
| `estado` | str | 100% | SP |
| `estoque` | int | 100% | 1788 |
| `garantia_do_produto` | str | 100% | Contra defeitos de fabricação |
| `ipi` | int/float | 100% | 6.5 |
| `matriz_de_categorias` | str | 100% | Copos, Canecas, Squeezes e Garrafas\|Lançamentos\|Garrafa Personalizada |
| `matriz_de_fotos_adicionais` | str | 100% | https://cdndeprodutos.azureedge.net/upload/imagens_site_v4/g/garrafa-em-alumini… |
| `ncm` | str | 100% | 76151000 |
| `peso_da_embalagem` | str | 100% | 147 g |
| `preco_com_gravacao_com_impostos` | float/int | 100% | (oculto: campo de preço) |
| `preco_com_gravacao_sem_impostos` | float/int | 100% | (oculto: campo de preço) |
| `preco_sem_gravacao_com_impostos` | float/int | 100% | (oculto: campo de preço) |
| `preco_sem_gravacao_sem_impostos` | float/int | 100% | (oculto: campo de preço) |
| `produto_ativo` | str | 100% | sim |
| `produtos_similares` | str | 100% | ;AS-00611\|#333b3b\|3459\|garrafa-em-aluminio-preto-600-ml_24346.webp\|GARRAFA EM A… |
| `quantidade_calculo_preco` | int | 100% | (oculto: campo de preço) |
| `quantidade_minima_sugerida` | int | 100% | 50 |
| `tipo_gravacao` | str | 100% | Uma gravação Silk/Digital. |
| `titulo` | str | 100% | GARRAFA EM ALUMÍNIO BRANCO - 600 ML |
| `url_foto` | str | 100% | https://cdndeprodutos.azureedge.net/upload/imagens_site_v4/g/garrafa-em-alumini… |

**3. Campos aninhados:** nenhum campo de lista de objetos encontrado no nível do produto.

**4. Candidato a identificador único:**
   - `codigo`: 1278 preenchidos, 1278 valores distintos → ÚNICO na amostra

**5. NCM:**
   - Presente no nível do produto: `ncm`

**6. Imagens (URL absoluta vs. caminho relativo):**
   - `matriz_de_fotos_adicionais`: URL absoluta
   - `url_foto`: URL absoluta

**7. Campo de data de atualização para sincronização incremental:**
   - Encontrado: `data_ultima_atualizacao`

**8. Produtos inativos/cancelados:**
   - Nenhum campo de status/ativo identificado; não foi possível determinar quantos produtos estão inativos.


## spot

Arquivos analisados: optionalscomplete_2026-09-04_1410.json, products_2026-09-04_1410.json, stocks_2026-09-04_1411.json

**1. Produtos na amostra:** 1247

**2. Campos no nível do produto:**

| Campo | Tipo | Preenchimento | Exemplo |
|---|---|---|---|
| `AditionalImageList` | — | 0% | — |
| `AllImageList` | str | 100% | 11103_103.jpg |
| `AvailableGross` | bool | 100% | True |
| `BagImage` | — | 0% | — |
| `BatteryType` | str | 1% | Inclui 2 pilhas AAA |
| `BoxHeightMM` | float | 100% | 0.34 |
| `BoxImage` | str | 21% | 51162_160-box.jpg |
| `BoxInnerQuantity` | int | 100% | 20 |
| `BoxLengthMM` | float | 100% | 0.39 |
| `BoxQuantity` | int | 100% | 500 |
| `BoxSizeM` | str | 100% | 0.390X0.220X0.340 |
| `BoxVolume` | float | 100% | 0.029 |
| `BoxWeightKG` | float | 100% | 15.0 |
| `BoxWidthMM` | float | 100% | 0.22 |
| `Brand` | str | 100% | hi!dea™ |
| `CapacityGB` | str | 74% | 0 |
| `CapacityMah` | str | 47% | 0 |
| `Capacitys` | str | 21% | 26 L |
| `Catalogs` | str | 100% | Stockout |
| `CertificateFiles` | str | 57% | cert_30500.zip |
| `Certificates` | str | 52% | Ftalatos, EN71 |
| `Colors` | str | 100% | Preto |
| `CombinedSizes` | str | 100% | 55 x 22 x 12 mm |
| `Composition` | str | 2% | Componentes entregues em separado |
| `CountryOfOrigin` | str | 97% | China |
| `CustomizationDefault` | str | 93% | (oculto: campo de preço) |
| `CustomizationDefaultHandlingCosts` | float/int | 100% | (oculto: campo de preço) |
| `CustomizationDefaultPrintingLines` | str | 91% | (oculto: campo de preço) |
| `CustomizationDefaultTable` | str | 93% | (oculto: campo de preço) |
| `CustomizationDefaultTableMaxColors` | int | 100% | (oculto: campo de preço) |
| `CustomizationDefaultType` | str | 93% | (oculto: campo de preço) |
| `CustomizationTableOptions` | str | 100% | (oculto: campo de preço) |
| `CustomizationTables` | str | 100% | (oculto: campo de preço) |
| `CustomizationTypes` | str | 100% | (oculto: campo de preço) |
| `DefaultCustomizationIncludedInPrice` | bool | 100% | (oculto: campo de preço) |
| `Description` | str | 100% | Borracha branca em TPR. Produto certificado de acordo com a portaria Inmetro nº… |
| `Gender` | — | 0% | — |
| `HasCapacitys` | bool | 100% | False |
| `HasColors` | bool | 100% | True |
| `HasSizes` | bool | 100% | False |
| `InkColor` | str | 2% | Preto |
| `IsSeasonal` | bool | 100% | False |
| `IsStockOut` | bool | 100% | True |
| `IsTextil` | bool | 100% | False |
| `KeyWords` | str | 100% | borracha, borrachas, rubber, material, escolar, escola, escritório, escritórios… |
| `MainImage` | str | 100% | 11103_103.jpg |
| `Materials` | str | 99% | TPR |
| `Multiplier` | int | 100% | 1 |
| `Name` | str | 100% | 11103. Borracha branca em TPR |
| `OnlineExclusive` | bool | 100% | False |
| `OtherDetails` | — | 0% | — |
| `Packing` | str | 68% | Polybag |
| `PaperGramage` | — | 0% | — |
| `PaperSize` | — | 0% | — |
| `PouchImage` | str | 5% | 51348_103-pouch.jpg |
| `ProdReference` | str | 100% | 11103 |
| `ProductCare` | — | 0% | — |
| `ProductComponentDefaultLocation` | str | 99% | Superior |
| `ProductComponentDefaultLocationAreaMM` | str | 93% | 45 x 10 |
| `ProductComponentLocations` | str | 100% | Superior |
| `ProductComponents` | str | 100% | Borracha |
| `ProductComposedLocations` | str | 100% | Borracha - Superior |
| `ProductDefaultComponent` | str | 100% | Borracha |
| `Properties` | str | 73% | Fornecido em caixa de oferta, LED, Carregador wireless |
| `PvcFree` | bool | 100% | False |
| `RefillType` | — | 0% | — |
| `RelatedReferences` | str | 85% | 51917 |
| `Repacking` | str | 70% | Sem polybag |
| `SEOName` | str | 100% | 11103 |
| `SEOShortDescription` | str | 100% | 11103. Borracha branca em TPR |
| `SEOShortDescriptionCap` | str | 100% | 11103. BORRACHA BRANCA EM TPR |
| `SeasonalEndDate` | — | 0% | — |
| `SeasonalOccasion` | — | 0% | — |
| `SeasonalStartDate` | — | 0% | — |
| `ShortDescription` | str | 100% | Borracha branca em TPR. Produto certificado de acordo com a portaria Inmetro nº… |
| `Sizes` | str | 1% | M, G, GG, P, XGG |
| `SubType` | str | 100% | Borrachas |
| `SubTypeCode` | str | 99% | 1571 |
| `Taric` | str | 100% | 4016.92.00 |
| `Type` | str | 100% | Escrita |
| `TypeCode` | str | 100% | 0031 |
| `UpdateDate` | str | 100% | 07/14/2026 07:55:00 |
| `Video360` | — | 0% | — |
| `VideoLink` | str | 16% | https://vimeo.com/1180873726 |
| `VideoLinkVimeo` | — | 0% | — |
| `Weight` | int | 100% | 1 |
| `WeightGr` | str | 10% | 80 g/m² |

**3. Campos aninhados:** nenhum campo de lista de objetos encontrado no nível do produto.

**4. Candidato a identificador único:**
   - `RefillType`: 0 preenchidos, 0 valores distintos → NÃO único / incompleto na amostra

**5. NCM:**
   - Não encontrado em nenhum nível.

**6. Imagens (URL absoluta vs. caminho relativo):**
   - `AditionalImageList`: sem valores de string para avaliar
   - `AllImageList`: caminho relativo
   - `BagImage`: sem valores de string para avaliar
   - `BoxImage`: caminho relativo
   - `MainImage`: caminho relativo
   - `PouchImage`: caminho relativo

**7. Campo de data de atualização para sincronização incremental:**
   - Encontrado: `UpdateDate`

**8. Produtos inativos/cancelados:**
   - Nenhum campo de status/ativo identificado; não foi possível determinar quantos produtos estão inativos.

**Datasets auxiliares neste fornecedor:**
   - `optionalscomplete`: 3709 registros

     | Campo | Tipo | Preenchimento | Exemplo |
     |---|---|---|---|
     | `AditionalImageList` | — | 0% | — |
     | `AllImageList` | str | 100% | 11103_103.jpg |
     | `Area1` | str | 100% | 45 x 10 |
     | `Area1Image` | str | 98% | 11103_1_1_1.png |
     | `Area2` | str | 87% | 50 x 40 |
     | `Area2Image` | str | 86% | 11104_1_2_3.png |
     | `Area3` | str | 65% | 35 x 25 |
     | `Area3Image` | str | 64% | 11104_1_1_1.png, 11104_1_1_2.png |
     | `Area4` | str | 53% | 40 x 5 |
     | `Area4Image` | str | 52% | 11110_1_4_2.png |
     | `Area5` | str | 37% | 45 x 5 |
     | `Area5Image` | str | 36% | 11110_1_4_1.png |
     | `Area6` | str | 31% | 270 x 260 |
     | `Area6Image` | str | 30% | 11125_1_4_1.png |
     | `Area7` | str | 25% | 50 x 400 |
     | `Area7Image` | str | 25% | 30500_1_13_2.png |
     | `Area8` | str | 22% | 50 x 500 |
     | `Area8Image` | str | 22% | 30500_1_13_1.png |
     | `AvailableGross` | bool | 100% | True |
     | `BagImage` | — | 0% | — |
     | `BatteryType` | str | 1% | Inclui 2 pilhas AAA |
     | `BoxHeightMM` | float | 100% | 0.34 |
     | `BoxImage` | str | 13% | 51162_160-box.jpg |
     | `BoxInnerQuantity` | int | 100% | 20 |
     | `BoxLengthMM` | float | 100% | 0.39 |
     | `BoxQuantity` | int | 100% | 500 |
     | `BoxSizeM` | str | 100% | 0.390X0.220X0.340 |
     | `BoxVolume` | float | 100% | 0.029 |
     | `BoxWeightKG` | float | 100% | 15.0 |
     | `BoxWidthMM` | float | 100% | 0.22 |
     | `Brand` | str | 100% | hi!dea™ |
     | `Capacity` | str | 21% | 26 L |
     | `CapacityGB` | str | 79% | 0 |
     | `CapacityMah` | str | 43% | 0 |
     | `Catalogs` | str | 100% | Stockout |
     | `CertificateFiles` | str | 66% | cert_30500.zip |
     | `Certificates` | str | 60% | Ftalatos, EN71 |
     | `ColorCode` | str | 100% | 103 |
     | `ColorDesc1` | str | 100% | Preto |
     | `ColorDesc2` | str | 0% | Cromado satinado |
     | `ColorHex1` | str | 100% | #000000 |
     | `ColorHex2` | — | 0% | — |
     | `CombinedSizes` | str | 100% | 55 x 22 x 12 mm |
     | `Component1` | str | 100% | Borracha |
     | `Component1Image` | str | 99% | 11103_103_C1.png |
     | `Component2` | str | 87% | Bateria portátil |
     | `Component2Image` | str | 87% | 11104_105_C1.png |
     | `Component3` | str | 65% | Bateria portátil |
     | `Component3Image` | str | 65% | 11104_105_C1.png |
     | `Component4` | str | 53% | Esferográfica |
     | `Component4Image` | str | 53% | 11110_105_C1.png |
     | `Component5` | str | 37% | Esferográfica |
     | `Component5Image` | str | 37% | 11110_105_C1.png |
     | `Component6` | str | 31% | Sacola |
     | `Component6Image` | str | 31% | 11125_105_C1.png |
     | `Component7` | str | 25% | T-shirt Manga curta |
     | `Component7Image` | str | 25% | 30500_102_C1.png |
     | `Component8` | str | 22% | T-shirt Manga curta |
     | `Component8Image` | str | 22% | 30500_102_C1.png |
     | `ComposedLocation1` | str | 100% | Borracha - Superior |
     | `ComposedLocation2` | str | 87% | Bateria portátil - Verso |
     | `ComposedLocation3` | str | 65% | Bateria portátil - Frente |
     | `ComposedLocation4` | str | 53% | Esferográfica - Corpo |
     | `ComposedLocation5` | str | 37% | Esferográfica - Corpo |
     | `ComposedLocation6` | str | 31% | Sacola - Verso |
     | `ComposedLocation7` | str | 25% | T-shirt Manga curta - Verso barra lateral esquerda |
     | `ComposedLocation8` | str | 22% | T-shirt Manga curta - Verso barra lateral esquerda |
     | `Composition` | str | 1% | Componentes entregues em separado |
     | `CountryOfOrigin` | str | 98% | China |
     | `CustomizationDefaultShortTable` | str | 95% | (oculto: campo de preço) |
     | `CustomizationDefaultTable` | str | 95% | (oculto: campo de preço) |
     | `CustomizationDefaultTableMaxColors` | int | 100% | (oculto: campo de preço) |
     | `CustomizationDefaultType` | str | 95% | (oculto: campo de preço) |
     | `CustomizationTableOptions` | str | 100% | (oculto: campo de preço) |
     | `CustomizationTables` | str | 100% | (oculto: campo de preço) |
     | `CustomizationTypes` | str | 100% | (oculto: campo de preço) |
     | `CustomizationTypes1` | str | 100% | (oculto: campo de preço) |
     | `CustomizationTypes2` | str | 87% | (oculto: campo de preço) |
     | `CustomizationTypes3` | str | 65% | (oculto: campo de preço) |
     | `CustomizationTypes4` | str | 53% | (oculto: campo de preço) |
     | `CustomizationTypes5` | str | 37% | (oculto: campo de preço) |
     | `CustomizationTypes6` | str | 31% | (oculto: campo de preço) |
     | `CustomizationTypes7` | str | 25% | (oculto: campo de preço) |
     | `CustomizationTypes8` | str | 22% | (oculto: campo de preço) |
     | `DefaultCustomization` | str | 95% | (oculto: campo de preço) |
     | `DefaultCustomizationHandlingCosts` | float/int | 100% | (oculto: campo de preço) |
     | `DefaultCustomizationIncludedInPrice` | bool | 100% | (oculto: campo de preço) |
     | `DefaultCustomizationPrintingLines` | str | 94% | (oculto: campo de preço) |
     | `Description` | str | 100% | Borracha branca em TPR. Produto certificado de acordo com a portaria Inmetro nº… |
     | `Gender` | — | 0% | — |
     | `HandlingCosts1` | str | 100% | 0.0 |
     | `HandlingCosts2` | str | 87% | 0.0 |
     | `HandlingCosts3` | str | 65% | 0.0, 0.0 |
     | `HandlingCosts4` | str | 53% | 0.0 |
     | `HandlingCosts5` | str | 37% | 0.0 |
     | `HandlingCosts6` | str | 31% | 0.0 |
     | `HandlingCosts7` | str | 25% | 0.0, 0.0 |
     | `HandlingCosts8` | str | 22% | 0.0 |
     | `HasCapacitys` | bool | 100% | False |
     | `HasColors` | bool | 100% | True |
     | `HasSizes` | bool | 100% | False |
     | `InkColor` | str | 2% | Preto |
     | `IsSeasonal` | bool | 100% | False |
     | `IsStockOut` | bool | 100% | True |
     | `IsTextil` | bool | 100% | False |
     | `KeyWords` | str | 100% | borracha, borrachas, rubber, material, escolar, escola, escritório, escritórios… |
     | `Location1` | str | 100% | Superior |
     | `Location1Image` | str | 98% | 11103_103_C1_L1.png |
     | `Location2` | str | 87% | Verso |
     | `Location2Image` | str | 86% | 11104_105_C1_L2.png |
     | `Location3` | str | 65% | Frente |
     | `Location3Image` | str | 64% | 11104_105_C1_L1.png |
     | `Location4` | str | 53% | Corpo |
     | `Location4Image` | str | 52% | 11110_105_C1_L4.png |
     | `Location5` | str | 37% | Corpo |
     | `Location5Image` | str | 36% | 11110_105_C1_L4.png |
     | `Location6` | str | 31% | Verso |
     | `Location6Image` | str | 30% | 11125_105_C1_L4.png |
     | `Location7` | str | 25% | Verso barra lateral esquerda |
     | `Location7Image` | str | 25% | 30500_102_C1_L13.png |
     | `Location8` | str | 22% | Verso barra lateral esquerda |
     | `Location8Image` | str | 22% | 30500_102_C1_L13.png |
     | `MainImage` | str | 100% | 11103_103.jpg |
     | `Materials` | str | 99% | TPR |
     | `MaxColors` | int | 86% | 1 |
     | `MaxColors1` | str | 100% | 0 |
     | `MaxColors2` | str | 87% | 0 |
     | `MaxColors3` | str | 65% | 1, 0 |
     | `MaxColors4` | str | 53% | 1 |
     | `MaxColors5` | str | 37% | 0 |
     | `MaxColors6` | str | 31% | 0 |
     | `MaxColors7` | str | 25% | 13, 0 |
     | `MaxColors8` | str | 22% | 0 |
     | `MaxHandlingCost` | — | 0% | — |
     | `MinQt1` | int | 100% | 1 |
     | `MinQt10` | — | 0% | — |
     | `MinQt2` | int | 93% | 11 |
     | `MinQt3` | int | 93% | 5100 |
     | `MinQt4` | int | 7% | 1050 |
     | `MinQt5` | — | 0% | — |
     | `MinQt6` | — | 0% | — |
     | `MinQt7` | — | 0% | — |
     | `MinQt8` | — | 0% | — |
     | `MinQt9` | — | 0% | — |
     | `Multiplier` | int | 100% | 1 |
     | `Name` | str | 100% | 11103. Borracha branca em TPR |
     | `NewProduct` | bool | 100% | False |
     | `NoReplenishment` | bool | 100% | False |
     | `OnlineExclusive` | bool | 100% | False |
     | `OptionalImage1` | str | 99% | 11103_103.jpg |
     | `OptionalImage2` | — | 0% | — |
     | `OtherDetails` | — | 0% | — |
     | `Packing` | str | 59% | Polybag |
     | `PaperGramage` | — | 0% | — |
     | `PaperSize` | — | 0% | — |
     | `PouchImage` | str | 3% | 51348_103-pouch.jpg |
     | `Price1` | float | 100% | (oculto: campo de preço) |
     | `Price10` | — | 0% | — |
     | `Price2` | float | 93% | (oculto: campo de preço) |
     | `Price3` | float | 93% | (oculto: campo de preço) |
     | `Price4` | float | 7% | (oculto: campo de preço) |
     | `Price5` | — | 0% | — |
     | `Price6` | — | 0% | — |
     | `Price7` | — | 0% | — |
     | `Price8` | — | 0% | — |
     | `Price9` | — | 0% | — |
     | `ProdReference` | str | 100% | 11103 |
     | `ProductCare` | — | 0% | — |
     | `ProductComponentDefaultLocation` | str | 99% | Superior |
     | `ProductComponentDefaultLocationAreaMM` | str | 95% | 45 x 10 |
     | `ProductComponentLocations` | str | 100% | Superior |
     | `ProductComponents` | str | 100% | Borracha |
     | `ProductComposedLocations` | str | 100% | Borracha - Superior |
     | `ProductDefaultComponent` | str | 100% | Borracha |
     | `Properties` | str | 77% | Fornecido em caixa de oferta, LED, Carregador wireless |
     | `PvcFree` | bool | 100% | False |
     | `RefillType` | — | 0% | — |
     | `RelatedReferences` | str | 88% | 51917 |
     | `Repacking` | str | 75% | Sem polybag |
     | `SEOName` | str | 100% | 11103 |
     | `SEOShortDescription` | str | 100% | 11103. Borracha branca em TPR |
     | `SEOShortDescriptionCap` | str | 100% | 11103. BORRACHA BRANCA EM TPR |
     | `SeasonalEndDate` | — | 0% | — |
     | `SeasonalOccasion` | — | 0% | — |
     | `SeasonalStartDate` | — | 0% | — |
     | `ShortDescription` | str | 100% | Borracha branca em TPR. Produto certificado de acordo com a portaria Inmetro nº… |
     | `Size` | str | 18% | G |
     | `SizeLengthCM` | float | 18% | 74.0 |
     | `SizeWidthCM` | float | 18% | 56.0 |
     | `Sku` | str | 100% | 11103-103 |
     | `SubType` | str | 100% | Borrachas |
     | `SubTypeCode` | str | 99% | 1571 |
     | `TableCodes1` | str | 100% | SCR1 |
     | `TableCodes2` | str | 87% | PDP2 |
     | `TableCodes3` | str | 65% | LSR1, PDP2 |
     | `TableCodes4` | str | 53% | LSR1 |
     | `TableCodes5` | str | 37% | PDP1 |
     | `TableCodes6` | str | 31% | TXP1 |
     | `TableCodes7` | str | 25% | TRD1, TRS1 |
     | `TableCodes8` | str | 22% | TXP6 |
     | `TableCodesOptions1` | str | 100% | SCR1-01-01 |
     | `TableCodesOptions2` | str | 87% | PDP2-01-01, PDP2-01-02, PDP2-01-03 |
     | `TableCodesOptions3` | str | 65% | LSR1-01-01, LSR1-02-01, LSR1-03-01, PDP2-01-01, PDP2-01-02, PDP2-01-03 |
     | `TableCodesOptions4` | str | 53% | LSR1-01-01 |
     | `TableCodesOptions5` | str | 37% | PDP1-01-01, PDP1-01-02 |
     | `TableCodesOptions6` | str | 31% | TXP1-01-01, TXP1-01-02, TXP1-01-03, TXP1-01-04, TXP1-02-01, TXP1-02-02, TXP1-02… |
     | `TableCodesOptions7` | str | 25% | TRD1-01-F, TRD1-02-F, TRD1-03-F, TRD1-04-F, TRD1-05-F, TRD1-06-F, TRS1-01-01, T… |
     | `TableCodesOptions8` | str | 22% | TXP6-01-01, TXP6-01-02, TXP6-01-03, TXP6-01-04 |
     | `TableFullCode1` | str | 100% | SCR1-01 |
     | `TableFullCode2` | str | 87% | PDP2-01 |
     | `TableFullCode3` | str | 65% | LSR1-01, PDP2-01 |
     | `TableFullCode4` | str | 53% | LSR1-01 |
     | `TableFullCode5` | str | 37% | PDP1-01 |
     | `TableFullCode6` | str | 31% | TXP1-01, TXP1-02 |
     | `TableFullCode7` | str | 25% | TRD1-01, TRS1-01, TRS1-02, TRS1-03, TRS1-04, TRS1-05, TRS1-06 |
     | `TableFullCode8` | str | 22% | TXP6-01 |
     | `Taric` | str | 100% | 4016.92.00 |
     | `Type` | str | 100% | Escrita |
     | `TypeCode` | str | 100% | 0031 |
     | `UpdateDate` | str | 100% | 07/14/2026 07:55:00 |
     | `Video360` | — | 0% | — |
     | `VideoLink` | str | 11% | https://vimeo.com/1180873726 |
     | `VideoLinkVimeo` | — | 0% | — |
     | `WebSku` | str | 100% | 11103-103 |
     | `Weight` | int | 100% | 1 |
     | `WeightGr` | str | 10% | 80 g/m² |
     | `YourPrice` | float | 7% | (oculto: campo de preço) |

   - `stocks`: 3709 registros

     | Campo | Tipo | Preenchimento | Exemplo |
     |---|---|---|---|
     | `Country` | — | 0% | — |
     | `NextDate1` | str | 19% | 2026-09-30 |
     | `NextDate2` | str | 4% | 2026-12-15 |
     | `NextDate3` | str | 0% | 2027-01-05 |
     | `NextDate4` | str | 0% | 2027-03-15 |
     | `NextDate5` | — | 0% | — |
     | `NextDate6` | — | 0% | — |
     | `NextQuantity1` | int | 19% | 70000 |
     | `NextQuantity2` | int | 4% | 3000 |
     | `NextQuantity3` | int | 0% | 7000 |
     | `NextQuantity4` | int | 0% | 3000 |
     | `NextQuantity5` | — | 0% | — |
     | `NextQuantity6` | — | 0% | — |
     | `Quantity` | int | 100% | 232535 |
     | `Sku` | str | 100% | 11103-103 |
     | `WebSku` | str | 100% | 11103-103 |

