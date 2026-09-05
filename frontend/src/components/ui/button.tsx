import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Slot } from "radix-ui"

/**
 * As 4 variantes de design/02-dashboard/DESIGN.md ("### Botões"):
 * Primary, Secondary/Outline, Ghost, Destructive. Cores e estados (hover,
 * active, focus) vêm literalmente da spec — não são aproximações do
 * default do shadcn.
 */
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-lg text-body-medium font-medium whitespace-nowrap transition-colors outline-none select-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-active",
        secondary:
          "border border-border bg-secondary text-secondary-foreground hover:border-border-hover hover:bg-accent",
        ghost: "text-muted-foreground hover:bg-secondary hover:text-foreground",
        destructive:
          "border border-destructive/30 bg-destructive-subtle text-destructive hover:bg-destructive hover:text-destructive-foreground",
      },
      size: {
        default: "h-8 px-3",
        sm: "h-7 px-2.5 text-caption-medium",
        icon: "size-8",
        "icon-sm": "size-7",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
