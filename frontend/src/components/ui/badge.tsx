import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/**
 * design/02-dashboard/DESIGN.md — "### Badges de Status & Chips":
 * altura 22px, padding horizontal 6px, radius 4px, 12px/500. Uma variante
 * por estado semântico — não é um badge genérico de rótulo.
 */
const badgeVariants = cva(
  "inline-flex h-[22px] w-fit shrink-0 items-center gap-1.5 rounded-sm border px-1.5 text-caption-medium whitespace-nowrap",
  {
    variants: {
      variant: {
        success: "border-success/20 bg-success-subtle text-success",
        warning: "border-warning/20 bg-warning-subtle text-warning",
        error: "border-error/20 bg-error-subtle text-error",
        neutral: "border-border bg-muted text-muted-foreground",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants>) {
  return (
    <span data-slot="badge" data-variant={variant} className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
