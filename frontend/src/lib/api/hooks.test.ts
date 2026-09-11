import { describe, expect, it } from "vitest"
import { instanciaTemSincronizacaoAtiva } from "./hooks"
import type { CadastroTinyEstadoEnum, FornecedorDetalhe, InstanciaDetalhe } from "./types"

function fornecedor(
  over: Partial<FornecedorDetalhe> & { estadoCadastroTiny?: CadastroTinyEstadoEnum } = {},
): FornecedorDetalhe {
  const { estadoCadastroTiny = "pronto", ...rest } = over
  return {
    fornecedor: "xbz",
    cor: "ok",
    ultima_execucao_em: null,
    ultima_execucao_status: null,
    ultima_execucao: null,
    produtos_total: 0,
    produtos_aguardando: 0,
    produtos_descontinuados: 0,
    credencial_configurada: true,
    credencial_ativa: true,
    cadastro_tiny: {
      execucao_id: 1,
      estado: estadoCadastroTiny,
      total_lidos: 0,
      total_cadastrados: 0,
      total_erros: 0,
      total_ignorados: 0,
      progresso: 0,
      atualizada_em: null,
      mensagem_erro: "",
      motivo_status: "",
      bloqueados: 0,
      falhas_secundarias: 0,
      pode_iniciar: false,
      pode_pausar: false,
      pode_retomar: false,
    },
    ...rest,
  }
}

function instancia(fornecedores: FornecedorDetalhe[]): InstanciaDetalhe {
  return { fornecedores } as InstanciaDetalhe
}

describe("instanciaTemSincronizacaoAtiva (dispara o polling do detalhe)", () => {
  it("false quando nada está ativo", () => {
    expect(instanciaTemSincronizacaoAtiva(undefined)).toBe(false)
    expect(
      instanciaTemSincronizacaoAtiva(instancia([fornecedor(), fornecedor({ estadoCadastroTiny: "pausado" })])),
    ).toBe(false)
    expect(
      instanciaTemSincronizacaoAtiva(instancia([fornecedor({ estadoCadastroTiny: "concluido" })])),
    ).toBe(false)
  })

  it("true quando um cadastro Tiny está sincronizando", () => {
    expect(
      instanciaTemSincronizacaoAtiva(
        instancia([fornecedor(), fornecedor({ fornecedor: "asia", estadoCadastroTiny: "sincronizando" })]),
      ),
    ).toBe(true)
  })

  it("true enquanto um cadastro Tiny está pausando (ainda tem task viva)", () => {
    expect(
      instanciaTemSincronizacaoAtiva(instancia([fornecedor({ estadoCadastroTiny: "pausando" })])),
    ).toBe(true)
  })

  it("true quando uma importação de espelho está rodando", () => {
    expect(
      instanciaTemSincronizacaoAtiva(instancia([fornecedor({ ultima_execucao_status: "rodando" })])),
    ).toBe(true)
  })
})
