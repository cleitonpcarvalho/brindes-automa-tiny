import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/**
 * Indicador circular de status (design/02-dashboard/DESIGN.md: "círculo
 * preenchido de 6px" nos badges, usado sozinho em tabelas/listas — ex.:
 * design/03-instancias e a lista de instâncias do dashboard).
 */
const statusDotVariants = cva("inline-block size-1.5 shrink-0 rounded-full", {
  variants: {
    variant: {
      success: "bg-success",
      warning: "bg-warning",
      error: "bg-error",
      neutral: "bg-neutral-status",
    },
  },
  defaultVariants: {
    variant: "neutral",
  },
})

interface StatusDotProps extends React.ComponentProps<"span">, VariantProps<typeof statusDotVariants> {
  /** Anel translúcido ao redor do ponto (design: usado em alertas críticos). */
  ring?: boolean
}

function StatusDot({ className, variant, ring = false, ...props }: StatusDotProps) {
  return (
    <span
      data-slot="status-dot"
      className={cn(
        statusDotVariants({ variant }),
        ring && "ring-4",
        ring && variant === "success" && "ring-success/20",
        ring && variant === "warning" && "ring-warning/20",
        ring && variant === "error" && "ring-error/20",
        ring && variant === "neutral" && "ring-neutral-status/20",
        className
      )}
      {...props}
    />
  )
}

export { StatusDot, statusDotVariants }
