import { Button } from "@/components/ui/button"
import { formatarNumero } from "@/lib/format"

interface Props {
  pagina: number
  totalPaginas: number
  totalItens: number
  itensNaPagina: number
  onPageChange: (pagina: number) => void
  /** Rótulo do que está sendo paginado (ex.: "instâncias", "variações"). */
  rotuloItens?: string
}

export function PaginationFooter({
  pagina,
  totalPaginas,
  totalItens,
  itensNaPagina,
  onPageChange,
  rotuloItens = "instâncias",
}: Props) {
  if (totalItens === 0) return null

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-1 text-caption-label text-muted-foreground">
      <span>
        Mostrando {itensNaPagina} de {formatarNumero(totalItens)} {rotuloItens}
      </span>
      <div className="flex items-center gap-1">
        <Button variant="secondary" size="sm" disabled={pagina <= 1} onClick={() => onPageChange(pagina - 1)}>
          Anterior
        </Button>
        <span className="px-2 tabular-nums">
          {pagina} / {totalPaginas}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={pagina >= totalPaginas}
          onClick={() => onPageChange(pagina + 1)}
        >
          Próximo
        </Button>
      </div>
    </div>
  )
}
