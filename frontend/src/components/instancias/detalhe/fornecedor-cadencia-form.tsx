"use client"

import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { ApiError } from "@/lib/api/client"
import { useAtualizarCadencia } from "@/lib/api/hooks"
import type { CadenciaFornecedor, FornecedorEnum } from "@/lib/api/types"

const OPCOES_INTERVALO = [
  { minutos: 60, rotulo: "A cada 1 hora" },
  { minutos: 120, rotulo: "A cada 2 horas" },
  { minutos: 240, rotulo: "A cada 4 horas" },
  { minutos: 720, rotulo: "A cada 12 horas" },
  { minutos: 1440, rotulo: "Diariamente" },
]

interface Props {
  fornecedor: FornecedorEnum
  cadencia: CadenciaFornecedor
  slug: string
}

export function FornecedorCadenciaForm({ fornecedor, cadencia, slug }: Props) {
  const atualizar = useAtualizarCadencia(slug, fornecedor)
  const mensagemErro = atualizar.error instanceof ApiError ? atualizar.error.message : null

  return (
    <div className="flex flex-col gap-4">
      <h3 className="text-caption-medium tracking-wide text-muted-foreground uppercase">Sincronização</h3>

      <div className="flex flex-col gap-1.5">
        <Label>Intervalo de sincronização</Label>
        <Select
          value={String(cadencia.intervalo_minutos ?? 60)}
          onValueChange={(valor) => atualizar.mutate({ intervalo_minutos: Number(valor) })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {OPCOES_INTERVALO.map((opcao) => (
              <SelectItem key={opcao.minutos} value={String(opcao.minutos)}>
                {opcao.rotulo}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center justify-between pt-1">
        <div>
          <p className="text-body-medium text-foreground">Sincronização ativa</p>
          <p className="text-caption-label text-muted-foreground">Executar rotina programada automaticamente</p>
        </div>
        <Switch
          aria-label="Sincronização ativa"
          checked={cadencia.ativo}
          onCheckedChange={(marcado) => atualizar.mutate({ ativo: marcado })}
        />
      </div>

      {mensagemErro && <p className="text-caption-label text-error">{mensagemErro}</p>}
    </div>
  )
}
