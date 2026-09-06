interface Props {
  nome: string
  cnpj?: string
  onEditar: () => void
}

/** design/04-instancia-nova — CompactSummaryStrip acima do card do passo atual. */
export function SummaryStrip({ nome, cnpj, onEditar }: Props) {
  return (
    <div className="mb-3 flex items-center justify-between px-1 py-2 text-caption-label text-muted-foreground">
      <div className="flex min-w-0 items-center gap-1.5 truncate">
        <span className="truncate font-medium text-foreground">{nome}</span>
        {cnpj && (
          <>
            <span>·</span>
            <span>{cnpj}</span>
          </>
        )}
        <span>·</span>
        <span className="text-foreground/80">Tiny ERP</span>
      </div>
      <button
        type="button"
        onClick={onEditar}
        className="ml-4 shrink-0 text-caption-label font-medium text-primary transition-colors hover:underline"
      >
        Editar
      </button>
    </div>
  )
}
