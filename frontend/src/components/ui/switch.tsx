"use client"

import * as React from "react"
import { cn } from "cn"
import { Switch as SwitchPrimitive } from "radix-ui"

/** design/02-dashboard/DESIGN.md — "Switch: Trilho 32x18px... Thumb 14x14px branco" */
function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer relative inline-flex h-[18px] w-8 shrink-0 items-center rounded-full transition-colors outline-none",
        "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
        "data-checked:bg-primary data-unchecked:bg-border",
        "data-disabled:cursor-not-allowed data-disabled:opacity-50",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-3.5 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform data-checked:translate-x-[15px]"
      />
    </SwitchPrimitive.Root>
  )
}

export { Switch }
