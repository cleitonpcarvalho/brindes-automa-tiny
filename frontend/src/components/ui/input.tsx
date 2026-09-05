import * as React from "react"
import { cn } from "cn"

/** design/02-dashboard/DESIGN.md — "### Campos de Entrada (Input Fields)" */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-background px-2.5 text-body-default text-foreground transition-colors outline-none",
        "placeholder:text-muted-foreground/60",
        "focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring",
        "disabled:pointer-events-none disabled:cursor-not-allowed disabled:border-border-subtle disabled:bg-secondary disabled:text-muted-foreground/40",
        "aria-invalid:border-destructive aria-invalid:ring-1 aria-invalid:ring-destructive",
        className
      )}
      {...props}
    />
  )
}

export { Input }
