"use client"

import { useRouter } from "next/navigation"
import { MoreVertical } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"

export function AcoesMenu({ slug }: { slug: string }) {
  const router = useRouter()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Ações de instância"
          onClick={(event) => event.stopPropagation()}
        >
          <MoreVertical size={16} />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" onClick={(event) => event.stopPropagation()}>
        <DropdownMenuItem onSelect={() => router.push(`/instancias/${slug}`)}>Ver detalhes</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
