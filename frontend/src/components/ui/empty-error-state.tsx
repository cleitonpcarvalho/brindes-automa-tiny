import { Button } from "@/components/ui/button"

interface EmptyStateProps {
  title: string
  description?: string
}

function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-1 px-4 py-10 text-center">
      <p className="text-body-default text-foreground">{title}</p>
      {description && <p className="text-caption-label text-muted-foreground">{description}</p>}
    </div>
  )
}

interface ErrorStateProps {
  title?: string
  onRetry: () => void
}

function ErrorState({ title = "Não foi possível carregar os dados.", onRetry }: ErrorStateProps) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
      <p className="text-body-default text-error">{title}</p>
      <Button variant="secondary" size="sm" onClick={onRetry}>
        Tentar de novo
      </Button>
    </div>
  )
}

export { EmptyState, ErrorState }
