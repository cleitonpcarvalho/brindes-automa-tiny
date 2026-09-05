#!/usr/bin/env python3
"""Analisa as amostras brutas salvas em samples/ e gera samples/RELATORIO.md.

Script descartável do passo zero do projeto brindes-automa-tiny. Não imprime
o JSON inteiro nem preços reais: apenas estrutura, tipos, percentual de
preenchimento e exemplos truncados (com preços ocultos).
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"
REPORT_PATH = SAMPLES_DIR / "RELATORIO.md"

FORNECEDORES = ["xbz", "asia", "somarcas", "spot"]

TS_RE = re.compile(r"_\d{4}-\d{2}-\d{2}_\d{4}$")
PRICE_RE = re.compile(r"pre[cç]o|price|valor|custo|venda|revenda|tabela", re.IGNORECASE)
ID_RE = re.compile(r"^(id|codigo|c[oó]digo|cod|sku|referencia|refer[eê]ncia|ref)\w*$", re.IGNORECASE)
NCM_RE = re.compile(r"ncm", re.IGNORECASE)
IMAGE_RE = re.compile(r"imag|foto|photo|picture|galeria|gallery", re.IGNORECASE)
UPDATED_RE = re.compile(r"atualiz|updated|modific|alterac|alterad|last_?update|dt_alter|data_alter", re.IGNORECASE)
STATUS_RE = re.compile(r"^(ativo|active|status|situacao|situa[cç][aã]o|cancelad\w*|inativ\w*)$", re.IGNORECASE)
PRODUCT_LIST_KEY_RE = re.compile(r"produto|product|item|dados|data|resultado|result|lista", re.IGNORECASE)


def truncate(value, n=80):
    s = str(value)
    if len(s) > n:
        return s[: n - 1] + "…"
    return s


def latest_files_by_base(supplier_dir: Path) -> dict:
    files = sorted(supplier_dir.glob("*.json"))
    bases = {}
    for f in files:
        base = TS_RE.sub("", f.stem)
        bases[base] = f  # sorted ascending por timestamp -> último sobrescreve = mais recente
    return bases


def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_list_of_dicts(data, _depth=0):
    if isinstance(data, list):
        if data and all(isinstance(x, dict) for x in data):
            return data
        return None
    if isinstance(data, dict):
        candidates = [(k, v) for k, v in data.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]
        if candidates:
            preferred = [kv for kv in candidates if PRODUCT_LIST_KEY_RE.search(kv[0])]
            pool = preferred or candidates
            pool.sort(key=lambda kv: len(kv[1]), reverse=True)
            return pool[0][1]
        if _depth < 2:
            for v in data.values():
                if isinstance(v, dict):
                    found = find_list_of_dicts(v, _depth + 1)
                    if found:
                        return found
    return None


def find_nested_list_fields(records):
    nested = defaultdict(list)
    products_with_field = Counter()
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for k, v in rec.items():
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
                nested[k].extend(v)
                products_with_field[k] += 1
    return nested, products_with_field


def analyze_records(records):
    total = len(records)
    all_keys = set()
    field_present = Counter()
    field_types = defaultdict(Counter)
    field_example = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        all_keys.update(rec.keys())
        for k, v in rec.items():
            if v is None or v == "":
                continue
            field_present[k] += 1
            field_types[k][type(v).__name__] += 1
            if k not in field_example:
                field_example[k] = "(oculto: campo de preço)" if PRICE_RE.search(k) else truncate(v)
    rows = []
    for k in sorted(all_keys):
        present = field_present.get(k, 0)
        pct = (present / total * 100) if total else 0
        types = "/".join(t for t, _ in field_types[k].most_common()) or "—"
        rows.append({
            "campo": k,
            "tipo": types,
            "preenchimento": f"{pct:.0f}%",
            "exemplo": field_example.get(k, "—"),
        })
    return rows, all_keys


def find_id_candidates(records, all_keys):
    total = len(records)
    results = []
    for k in sorted(all_keys):
        if not ID_RE.match(k):
            continue
        values = [rec.get(k) for rec in records if isinstance(rec, dict) and rec.get(k) not in (None, "")]
        unique = len(set(map(str, values)))
        results.append({
            "campo": k,
            "preenchidos": len(values),
            "unicos": unique,
            "e_unico": bool(values) and unique == len(values) == total,
        })
    return results


def check_ncm(all_keys, nested):
    at_product = sorted(k for k in all_keys if NCM_RE.search(k))
    at_nested = {nk: sorted(k for k in items[0].keys() if NCM_RE.search(k)) for nk, items in nested.items() if items}
    at_nested = {nk: ks for nk, ks in at_nested.items() if ks}
    return at_product, at_nested


def check_images(records, all_keys):
    image_fields = sorted(k for k in all_keys if IMAGE_RE.search(k))
    findings = []
    for k in image_fields:
        samples = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            v = rec.get(k)
            if isinstance(v, str) and v:
                samples.append(v)
            elif isinstance(v, list):
                samples.extend(x for x in v if isinstance(x, str) and x)
            if len(samples) >= 20:
                break
        if not samples:
            findings.append((k, "sem valores de string para avaliar"))
            continue
        absolutos = sum(1 for s in samples if s.startswith("http://") or s.startswith("https://"))
        if absolutos == len(samples):
            findings.append((k, "URL absoluta"))
        elif absolutos == 0:
            findings.append((k, "caminho relativo"))
        else:
            findings.append((k, f"misto ({absolutos}/{len(samples)} absolutos)"))
    return findings


def check_updated_field(all_keys):
    return sorted(k for k in all_keys if UPDATED_RE.search(k))


def check_status_fields(records, all_keys):
    status_fields = sorted(k for k in all_keys if STATUS_RE.match(k))
    findings = []
    for k in status_fields:
        values = Counter()
        for rec in records:
            if isinstance(rec, dict) and k in rec:
                values[repr(rec[k])] += 1
        findings.append((k, values.most_common()))
    return findings


def get_main_records(fornecedor, datasets):
    if fornecedor == "asia":
        combined = []
        for base in sorted(b for b in datasets if b.startswith("produtos_pagina")):
            found = find_list_of_dicts(datasets[base])
            if found:
                combined.extend(found)
        aux = {b: v for b, v in datasets.items() if not b.startswith("produtos_pagina")}
        return combined, aux
    if fornecedor == "spot":
        main = find_list_of_dicts(datasets.get("products")) if "products" in datasets else None
        aux = {b: v for b, v in datasets.items() if b != "products"}
        return main or [], aux
    main = None
    aux = {}
    for b, v in datasets.items():
        found = find_list_of_dicts(v)
        if found and main is None:
            main = found
        else:
            aux[b] = v
    return main or [], aux


def render_table(rows):
    lines = ["| Campo | Tipo | Preenchimento | Exemplo |", "|---|---|---|---|"]
    for row in rows:
        exemplo = str(row["exemplo"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{row['campo']}` | {row['tipo']} | {row['preenchimento']} | {exemplo} |")
    return lines


def render_supplier(fornecedor, dir_path: Path):
    lines = [f"## {fornecedor}", ""]
    bases = latest_files_by_base(dir_path)
    if not bases:
        lines.append("Nenhuma amostra encontrada. Fornecedor pulado ou coleta falhou — ver saída de fetch_samples.py.")
        return lines

    datasets = {}
    for base, path in bases.items():
        try:
            datasets[base] = load_json(path)
        except (json.JSONDecodeError, OSError) as exc:
            lines.append(f"Falha ao ler `{path.name}`: {exc}")

    lines.append(f"Arquivos analisados: {', '.join(p.name for p in bases.values())}")
    lines.append("")

    main_records, aux_datasets = get_main_records(fornecedor, datasets)

    if not main_records:
        lines.append("Não foi possível localizar uma lista de produtos nos arquivos acima (estrutura inesperada).")
        return lines

    nested, products_with_field = find_nested_list_fields(main_records)

    # 1. quantidade
    lines.append(f"**1. Produtos na amostra:** {len(main_records)}")
    for nk, items in nested.items():
        lines.append(f"   - Variações/itens em `{nk}`: {len(items)} no total, presentes em {products_with_field[nk]} produtos")
    lines.append("")

    # 2. campos nível produto
    lines.append("**2. Campos no nível do produto:**")
    lines.append("")
    rows, all_keys = analyze_records(main_records)
    lines.extend(render_table(rows))
    lines.append("")

    # 3. campos aninhados
    if nested:
        lines.append("**3. Campos aninhados:**")
        for nk, items in nested.items():
            lines.append("")
            lines.append(f"_Nível `{nk}`_")
            lines.append("")
            nrows, _ = analyze_records(items)
            lines.extend(render_table(nrows))
    else:
        lines.append("**3. Campos aninhados:** nenhum campo de lista de objetos encontrado no nível do produto.")
    lines.append("")

    # 4. identificador único
    lines.append("**4. Candidato a identificador único:**")
    id_candidates = find_id_candidates(main_records, all_keys)
    if id_candidates:
        for c in id_candidates:
            veredito = "ÚNICO na amostra" if c["e_unico"] else "NÃO único / incompleto na amostra"
            lines.append(f"   - `{c['campo']}`: {c['preenchidos']} preenchidos, {c['unicos']} valores distintos → {veredito}")
    else:
        lines.append("   - Nenhum campo com nome típico de identificador (id/codigo/sku/referencia) encontrado.")
    lines.append("")

    # 5. NCM
    ncm_product, ncm_nested = check_ncm(all_keys, nested)
    lines.append("**5. NCM:**")
    if ncm_product:
        lines.append(f"   - Presente no nível do produto: {', '.join(f'`{k}`' for k in ncm_product)}")
    if ncm_nested:
        for nk, ks in ncm_nested.items():
            lines.append(f"   - Presente no nível `{nk}`: {', '.join(f'`{k}`' for k in ks)}")
    if not ncm_product and not ncm_nested:
        lines.append("   - Não encontrado em nenhum nível.")
    lines.append("")

    # 6. imagens
    lines.append("**6. Imagens (URL absoluta vs. caminho relativo):**")
    image_findings = check_images(main_records, all_keys)
    if image_findings:
        for k, veredito in image_findings:
            lines.append(f"   - `{k}`: {veredito}")
    else:
        lines.append("   - Nenhum campo de imagem identificado no nível do produto.")
    lines.append("")

    # 7. data de atualização
    lines.append("**7. Campo de data de atualização para sincronização incremental:**")
    updated_fields = check_updated_field(all_keys)
    if updated_fields:
        lines.append(f"   - Encontrado: {', '.join(f'`{k}`' for k in updated_fields)}")
    else:
        lines.append("   - Nenhum campo de data de atualização identificado no nível do produto.")
    lines.append("")

    # 8. inativos/cancelados
    lines.append("**8. Produtos inativos/cancelados:**")
    status_findings = check_status_fields(main_records, all_keys)
    if status_findings:
        for k, counts in status_findings:
            counts_str = ", ".join(f"{v}={n}" for v, n in counts)
            lines.append(f"   - `{k}`: distribuição de valores → {counts_str}")
    else:
        lines.append("   - Nenhum campo de status/ativo identificado; não foi possível determinar quantos produtos estão inativos.")
    lines.append("")

    # datasets auxiliares (ex.: spot optionalsComplete/stocks)
    if aux_datasets:
        lines.append("**Datasets auxiliares neste fornecedor:**")
        for base, data in aux_datasets.items():
            records = find_list_of_dicts(data)
            if records is None:
                lines.append(f"   - `{base}`: estrutura não identificada como lista de registros.")
                continue
            lines.append(f"   - `{base}`: {len(records)} registros")
            arows, _ = analyze_records(records)
            lines.append("")
            lines.extend(f"     {l}" for l in render_table(arows))
            lines.append("")

    return lines


def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    report_lines = [
        "# Relatório de amostras das APIs de fornecedores",
        "",
        "Gerado por `tools/analyze_samples.py`. Não contém preços reais nem o JSON bruto —",
        "apenas estrutura, tipos e percentuais de preenchimento.",
        "",
    ]

    for fornecedor in FORNECEDORES:
        dir_path = SAMPLES_DIR / fornecedor
        section = render_supplier(fornecedor, dir_path)
        report_lines.extend(section)
        report_lines.append("")

    report_text = "\n".join(report_lines)
    print(report_text)

    REPORT_PATH.write_text(report_text, encoding="utf-8")
    print(f"\nRelatório salvo em {REPORT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
