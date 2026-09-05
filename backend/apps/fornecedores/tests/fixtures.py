"""
Recortes reais de samples/{xbz,asia,spot}/ (campos relevantes para os
normalizadores, valores tais como vieram da API). Usados pelos testes do
app fornecedores para não depender de dados inventados.

Preços reais aparecem aqui de propósito — diferente de samples/RELATORIO.md
(que nunca deve conter preço real), estes arquivos são código de teste
interno do backend, não um relatório compartilhável.
"""

# samples/xbz/produtos_2026-09-04_1413.json — grupo CodigoAmigavel="06520"
# (Caneca Acrílica 400ml, 6 cores), usado para testar o agrupamento por
# CodigoAmigavel.
XBZ_GRUPO_06520 = [
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000019",
        "CodigoComposto": "06520-AZU",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "AZUL",
        "CorWebSecundaria": "AZUL",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 5690,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/6520-AZU-Caneca-400ml-Acrilica-249.jpg",
    },
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000477",
        "CodigoComposto": "06520-VD",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "VERDE",
        "CorWebSecundaria": "INOX",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 1775,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/6520-VD-Caneca-400ml-Acrilica-253.jpg",
    },
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000485",
        "CodigoComposto": "06520-BCO",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "BRANCO",
        "CorWebSecundaria": "INOX",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 9344,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/6520-BRA-Caneca-400ml-Acrilica-250.jpg",
    },
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000493",
        "CodigoComposto": "06520-LAR",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "LARANJA",
        "CorWebSecundaria": "INOX",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 4389,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/6520-LAR-Caneca-400ml-Acrilica-251.jpg",
    },
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000507",
        "CodigoComposto": "06520-TRA",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "TRANSPARENTE",
        "CorWebSecundaria": "INOX",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 7955,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/6520-TRA-Caneca-400ml-Acrilica-252.jpg",
    },
    {
        "CodigoAmigavel": "06520",
        "CodigoXbz": "X000515",
        "CodigoComposto": "06520-VM",
        "Nome": "CANECA ACRÍLICA 400 ML COM TAMPA",
        "Descricao": "Caneca acrílica 400ml com detalhe oval no pegador, revestimento interno e "
        "detalhes em inox. Tampa plástica resistente com sistema giratório para abertura(não é "
        "térmica).",
        "CorWebPrincipal": "VERMELHO",
        "CorWebSecundaria": "INOX",
        "Ncm": "73239300",
        "PrecoVenda": 10.9,
        "QuantidadeDisponivel": 70,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/Caneca-acrilica-400ml-VERMELHO-254-1645017532.jpg",
    },
]

# samples/xbz/produtos_2026-09-04_1413.json — grupo CodigoAmigavel="P@12288"
# (Galão Dobrável 3 Litros), usado para testar a regra do prefixo "P@".
XBZ_GRUPO_P12288 = [
    {
        "CodigoAmigavel": "P@12288",
        "CodigoXbz": "X000736",
        "CodigoComposto": "P@12288-AZE",
        "Nome": "GALÃO DOBRÁVEL 3 LITROS ",
        "Descricao": "Galão dobrável de plástico com 3 litros. Galão colorido com pegador plástico "
        "superior, acompanha torneira plástica com lacre, basta removê-lo e encaixá-lo no suporte "
        "inferior pressionando pra dentro. Para utilização da torneira levante as hastes laterais.",
        "CorWebPrincipal": "AZUL",
        "CorWebSecundaria": "AZUL",
        "Ncm": "39269090",
        "PrecoVenda": 2.99,
        "QuantidadeDisponivel": 6152,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/Galao-Dobravel-3-Litros-AZUL-14229-1650638150.jpg",
    },
    {
        "CodigoAmigavel": "P@12288",
        "CodigoXbz": "X000973",
        "CodigoComposto": "P@12288-PRE/BCO",
        "Nome": "GALÃO DOBRÁVEL 3 LITROS BOLINHAS ",
        "Descricao": "Galão dobrável de plástico com 3 litros. Galão colorido com pegador plástico "
        "superior, acompanha torneira plástica com lacre, basta removê-lo e encaixá-lo no suporte "
        "inferior pressionando pra dentro. Para utilização da torneira levante as hastes laterais.",
        "CorWebPrincipal": "PRETO",
        "CorWebSecundaria": "BRANCO",
        "Ncm": "39249000",
        "PrecoVenda": 2.99,
        "QuantidadeDisponivel": 7252,
        "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/Galao-Dobravel-3-Litros-13419d2-1631115329.jpg",
    },
]

# samples/asia/produtos_pagina1_2026-09-04_1410.json — produto "MC511P" com
# variação "MC511" (mesmo código, sem o "P"). Usado para testar o caso
# documentado do sufixo "P".
ASIA_PRODUTO_MC511P = {
    "referencia": "MC511P",
    "nome": "Bolsa Multifuncional em Poliéster 300D",
    "altura": 45,
    "largura": 38,
    "comprimento": 39,
    "peso": 0.868,
    "descricao": "Bolsa multifuncional em poliéster 300D com detalhes em PU e interior em 210D. "
    "Possui 2 compartimentos laterais, 3 bolsos frontais com zíper, 1 na parte oposta com "
    "fechamento em velcro, incluindo um específico para lenços umedecidos. Conta com alças de "
    "ombro e de mão com acabamento em PU, além de interior espaçoso com divisórias e fechamento "
    "em zíper. Prática e organizada para o dia a dia.",
    "categorias": {
        "277": "Bolsas &amp; Mochilas Maternidade",
        "105": "Mochilas",
        "186": "Mochilas &amp; Malas",
    },
    "imagem": "https://media.asiaimport.com.br/2024/05/Perfil_novo-30.jpg",
    "galeria": [
        "https://media.asiaimport.com.br/2024/05/IMG_7218.jpg",
        "https://media.asiaimport.com.br/2024/05/IMG_7225.jpg",
    ],
    "propriedades": {
        "dimensao-produto": "39x42x18cm (AxLxP)",
        "peso-do-produto": "0,868kg",
        "quant-por-caixa": "20pçs",
        "embalagem": "Saco Plástico Zip",
        "dimensao-da-caixa": "39x38x45cm",
        "peso-da-caixa": "20kgs",
        "volume": "29L",
        "ncm": "4202.92.00",
    },
    "variacoes": [
        {
            "referencia": "MC511",
            "nome": "Bolsa Multifuncional em Poliéster 300D",
            "ncm": "4202.92.00",
            "preco": "89",
            "qtd_estoque": 675,
            "imagem": "https://media.asiaimport.com.br/2024/05/IMG_7230.jpg",
            "atributos": {
                "cor": {"name": "cinza", "value": "Cinza", "hexadecimal": "#7f7f7f"},
                "volume-litros": {"name": "29l", "value": "29L"},
            },
        }
    ],
}

# Metadados reais da paginação da asia (samples/asia/produtos_pagina1_...json)
ASIA_META_PAGINACAO = {"pagina": 1, "total_paginas": 5, "por_pagina": 100, "total_produtos": 475}

# samples/spot/{products,optionalscomplete,stocks}_...json — ProdReference
# "11112" (Mochila para notebook), 2 cores. Usado para testar o join das
# três fontes.
SPOT_PRODUTO_11112 = {
    "ProdReference": "11112",
    "Name": "11112. Mochila para notebook 15'6'' em 1680D e 300D",
    "Description": "Mochila para notebook em 1680D e 300D com dois compartimentos. Compartimento "
    "principal com divisória almofadada para notebook até 15'6''. Interior forrado.",
    "Type": "Mochilas, Pastas & Sacolas",
    "SubType": "Mochilas para PC/ Tablet",
    "MainImage": "11112_115.jpg",
    "Taric": "4202.92.00",
    "UpdateDate": "07/14/2026 07:55:00",
    "Colors": "Azul, Bordô",
}

SPOT_OPCIONAIS_11112 = [
    {
        "Sku": "11112-104",
        "WebSku": "11112-104",
        "ProdReference": "11112",
        "ColorDesc1": "Azul",
        "ColorCode": "104",
        "Price1": 69.9,
        "MainImage": "11112_115.jpg",
        "Taric": "4202.92.00",
    },
    {
        "Sku": "11112-115",
        "WebSku": "11112-115",
        "ProdReference": "11112",
        "ColorDesc1": "Bordô",
        "ColorCode": "115",
        "Price1": 69.9,
        "MainImage": "11112_115.jpg",
        "Taric": "4202.92.00",
    },
]

SPOT_ESTOQUES_11112 = [
    {"Sku": "11112-104", "WebSku": "11112-104", "Quantity": 4669},
    {"Sku": "11112-115", "WebSku": "11112-115", "Quantity": 52},
]

# samples/somarcas/produtos_2026-09-04_1632.json — códigos reais (Garrafa em
# alumínio), um com estoque positivo e outro com estoque zero.
SOMARCAS_ITEM_COM_ESTOQUE = {
    "codigo": "AS-00610",
    "titulo": "GARRAFA EM ALUMÍNIO BRANCO - 600 ML",
    "descricao": "Garrafa em alumínio branco.\nConta com tampa plástica rosqueável preta com alça.",
    "url_foto": "https://cdndeprodutos.azureedge.net/upload/imagens_site_v4/g/garrafa-em-aluminio-branco-600-ml_24288.webp",
    "ncm": "76151000",
    "estoque": 1788,
    "estado": "SP",
    "preco_sem_gravacao_sem_impostos": 18.38,
    "preco_com_gravacao_sem_impostos": 19.73,
    "preco_sem_gravacao_com_impostos": 19.58,
    "preco_com_gravacao_com_impostos": 21.01,
    "produto_ativo": "sim",
    "matriz_de_categorias": "Copos, Canecas, Squeezes e Garrafas|Lançamentos|Garrafa Personalizada",
    "matriz_de_fotos_adicionais": "https://cdndeprodutos.azureedge.net/upload/imagens_site_v4/g/garrafa-em-aluminio-branco-600-ml_24342.webp",
    "data_ultima_atualizacao": "2026-09-04 11:51:45",
    "tipo_gravacao": "Uma gravação Silk/Digital.",
    "dimensoes_do_produto": "24,5x7cm",
    "dimensoes_da_embalagem": "0x0x0 mm (AxLxP)",  # "0x0x0" = não informado, na prática
    "peso_da_embalagem": "147 g",
    "embalagem_do_produto": "Caixa Preta",
    "garantia_do_produto": "Contra defeitos de fabricação",
    "ipi": 6.5,
    "quantidade_minima_sugerida": 50,
}

# samples/somarcas/ — "AS-01510" (Squeeze em Alumínio), com dimensões de
# embalagem REAIS (não zeradas) para testar a conversão mm -> cm.
SOMARCAS_ITEM_COM_DIMENSOES_REAIS = {
    "codigo": "AS-01510",
    "titulo": "SQUEEZE EM ALUMÍNIO BRANCO - 500 ML",
    "descricao": "Squeeze em alumínio branco, 500ml.",
    "url_foto": "https://cdndeprodutos.azureedge.net/upload/imagens_site_v4/g/squeeze-em-aluminio-branco-500-ml.webp",
    "ncm": "76151000",
    "estoque": 500,
    "estado": "SP",
    "preco_sem_gravacao_sem_impostos": 10.0,
    "preco_com_gravacao_sem_impostos": 11.0,
    "preco_sem_gravacao_com_impostos": 12.0,
    "preco_com_gravacao_com_impostos": 13.0,
    "produto_ativo": "sim",
    "matriz_de_categorias": "Copos, Canecas, Squeezes e Garrafas",
    "matriz_de_fotos_adicionais": "",
    "data_ultima_atualizacao": "2026-09-04 11:51:45",
    "tipo_gravacao": "Uma gravação Silk/Digital.",
    "dimensoes_do_produto": "21x6,5Øcm",
    "dimensoes_da_embalagem": "70x215x70 mm (AxLxP)",
    "peso_da_embalagem": "125 g",
    "embalagem_do_produto": "Caixa Branca",
    "garantia_do_produto": "",
    "ipi": 6.5,
    "quantidade_minima_sugerida": 20,
}

# samples/xbz/ — "GARRAFA TÉRMICA INOX 350ML C/ CAPA" (X000256), com
# Altura/Largura reais (não zeradas) e Peso — para testar a conversão
# grama -> kg (dimensões já vêm em cm, sem conversão).
XBZ_LINHA_COM_DIMENSOES = {
    "CodigoAmigavel": "01115",
    "CodigoXbz": "X000256",
    "CodigoComposto": "01115-INO",
    "Nome": "GARRAFA TÉRMICA INOX 350ML C/ CAPA",
    "Descricao": "Garrafa térmica em aço inox com capa.",
    "CorWebPrincipal": "INOX",
    "CorWebSecundaria": "INOX",
    "Ncm": "96170010",
    "PrecoVenda": 20.9,
    "QuantidadeDisponivel": 1259,
    "Peso": 274.0,
    "Altura": 20.0,
    "Largura": 21.5,
    "Profundidade": 0.0,  # 0.0 = não informado, tratado como None
    "ImageLink": "https://cdn.xbzbrindes.com.br/img/produtos/3/1115_INO.jpg",
}

# samples/spot/products_...json — "11110. Caneta esferográfica" com
# CombinedSizes no formato "ø<diametro> x <comprimento> mm", o único
# padrão de dimensão da Spot com eixo explícito (diâmetro).
SPOT_PRODUTO_CANETA_DIAMETRO = {
    "ProdReference": "11110",
    "Name": "11110. Caneta esferográfica com mecanismo twist",
    "Description": "Caneta esferográfica com mecanismo twist.",
    "Type": "Escrita",
    "SubType": "Canetas",
    "MainImage": "11110_105.jpg",
    "Taric": "",
    "UpdateDate": "07/14/2026 07:55:00",
    "CombinedSizes": "ø7 x 129 mm",
}

SPOT_OPCIONAL_CANETA = {
    "Sku": "11110-105",
    "WebSku": "11110-105",
    "ProdReference": "11110",
    "ColorDesc1": "Preto",
    "ColorCode": "105",
    "Price1": 3.5,
    "MainImage": "11110_105.jpg",
    "Taric": "",
}

SPOT_ESTOQUE_CANETA = {"Sku": "11110-105", "WebSku": "11110-105", "Quantity": 1118}
