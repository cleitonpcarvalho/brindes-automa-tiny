interface Props {
  titulo: string
  subtitulo: string
  children: React.ReactNode
  footer: React.ReactNode
}

/** Casca comum dos 3 cards do wizard — estilo replicado do card do passo 3 (único com mockup completo). */
export function WizardCard({ titulo, subtitulo, children, footer }: Props) {
  return (
    <div className="rounded-xl border border-border bg-card p-7">
      <header className="mb-6">
        <h1 className="text-title-page-mobile text-foreground">{titulo}</h1>
        <p className="mt-1.5 text-body-default text-muted-foreground">{subtitulo}</p>
      </header>

      {children}

      <footer className="mt-6 flex items-center justify-between border-t border-border pt-6">{footer}</footer>
    </div>
  )
}
