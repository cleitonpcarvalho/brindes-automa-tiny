import type { ComponentProps } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import * as hooks from "@/lib/api/hooks"
import { ApiError } from "@/lib/api/client"
import { FornecedorCadastroTiny } from "./fornecedor-cadastro-tiny"
import type { CadastroTinyEstado, CadastroTinyEstadoEnum } from "@/lib/api/types"

vi.mock("@/lib/api/hooks", () => ({
  useCadastroTinyPreview: vi.fn(),
  useCadastrarProdutosTiny: vi.fn(),
  usePausarCadastroTiny: vi.fn(),
  useRetomarCadastroTiny: vi.fn(),
}))

const pausarMutate = vi.fn()
const retomarMutate = vi.fn()
const cadastrarMutateAsync = vi.fn()

function mutacao(mutate = vi.fn(), extra: Record<string, unknown> = {}) {
  return { mutate, mutateAsync: vi.fn(), isPending: false, isError: false, error: null, ...extra } as never
}

function estadoBase(estado: CadastroTinyEstadoEnum, over: Partial<CadastroTinyEstado> = {}): CadastroTinyEstado {
  const flags = {
    pronto: { pode_iniciar: true, pode_pausar: false, pode_retomar: false },
    sincronizando: { pode_iniciar: false, pode_pausar: true, pode_retomar: false },
    pausando: { pode_iniciar: false, pode_pausar: false, pode_retomar: false },
    pausado: { pode_iniciar: false, pode_pausar: false, pode_retomar: true },
    interrompido: { pode_iniciar: false, pode_pausar: false, pode_retomar: true },
    concluido: { pode_iniciar: true, pode_pausar: false, pode_retomar: false },
    parcial: { pode_iniciar: true, pode_pausar: false, pode_retomar: false },
  }[estado]
  return {
    execucao_id: estado === "pronto" ? null : 7,
    estado,
    total_lidos: 100,
    total_cadastrados: 40,
    total_erros: 2,
    total_ignorados: 58,
    progresso: 0.42,
    atualizada_em: "2026-01-01T00:00:00Z",
    mensagem_erro: "",
    motivo_status: "",
    bloqueados: 0,
    falhas_secundarias: 0,
    ...flags,
    ...over,
  }
}

function renderComp(props: Partial<ComponentProps<typeof FornecedorCadastroTiny>> = {}) {
  return render(
    <FornecedorCadastroTiny
      slug="loja-x"
      fornecedor="xbz"
      estado={estadoBase("pronto")}
      {...props}
    />,
  )
}

describe("FornecedorCadastroTiny — estados e ações", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(hooks.usePausarCadastroTiny).mockReturnValue(mutacao(pausarMutate))
    vi.mocked(hooks.useRetomarCadastroTiny).mockReturnValue(mutacao(retomarMutate))
    vi.mocked(hooks.useCadastrarProdutosTiny).mockReturnValue(mutacao(vi.fn(), { mutateAsync: cadastrarMutateAsync }))
    vi.mocked(hooks.useCadastroTinyPreview).mockReturnValue({ data: undefined, isLoading: false, isError: false } as never)
  })

  it("PRONTO: só o botão 'Sincronizar com Tiny'", () => {
    renderComp({ estado: estadoBase("pronto") })
    expect(screen.getByRole("button", { name: "Sincronizar com Tiny" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Pausar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Retomar/ })).not.toBeInTheDocument()
  })

  it("SINCRONIZANDO: badge, progresso e só 'Pausar'", () => {
    renderComp({ estado: estadoBase("sincronizando") })
    expect(screen.getByText("Sincronizando")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42")
    expect(screen.getByText("40")).toBeInTheDocument() // cadastrados
    const pausar = screen.getByRole("button", { name: "Pausar" })
    fireEvent.click(pausar)
    expect(pausarMutate).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: /Sincronizar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Retomar/ })).not.toBeInTheDocument()
  })

  it("o 3º número é 'a fazer' enquanto roda e 'não cadastrados' quando conclui", () => {
    const { rerender } = renderComp({
      estado: estadoBase("sincronizando", { total_ignorados: 710 }),
    })
    expect(screen.getByText("710")).toBeInTheDocument()
    expect(screen.getByText("a fazer")).toBeInTheDocument()
    expect(screen.queryByText(/bloquead/i)).not.toBeInTheDocument()

    rerender(
      <FornecedorCadastroTiny
        slug="loja-x"
        fornecedor="xbz"
        estado={estadoBase("parcial", { total_ignorados: 12 })}
      />,
    )
    expect(screen.getByText("não cadastrados")).toBeInTheDocument()
  })

  it("recebe novos números por atualização de props (polling) e a barra acompanha", () => {
    const { rerender } = renderComp({
      estado: estadoBase("sincronizando", {
        total_cadastrados: 0,
        total_erros: 0,
        total_ignorados: 1137,
        progresso: 0,
      }),
    })
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "0")

    rerender(
      <FornecedorCadastroTiny
        slug="loja-x"
        fornecedor="xbz"
        estado={estadoBase("sincronizando", {
          total_cadastrados: 421,
          total_erros: 6,
          total_ignorados: 710,
          progresso: 0.376,
        })}
      />,
    )
    expect(screen.getByText("421")).toBeInTheDocument()
    expect(screen.getByText("6")).toBeInTheDocument()
    expect(screen.getByText("710")).toBeInTheDocument()
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "38")
  })

  it("PAUSANDO: nenhum botão de ação, texto 'terminando o produto atual'", () => {
    renderComp({ estado: estadoBase("pausando") })
    expect(screen.getByText("Pausando…")).toBeInTheDocument()
    expect(screen.getByText(/Terminando o produto atual/)).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Pausar|Retomar|Sincronizar/ })).not.toBeInTheDocument()
  })

  it("PAUSADO: badge, progresso e só 'Retomar'; clique retoma", () => {
    renderComp({ estado: estadoBase("pausado") })
    expect(screen.getByText("Pausado")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Retomar" }))
    expect(retomarMutate).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("button", { name: /Pausar/ })).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Sincronizar/ })).not.toBeInTheDocument()
  })

  it("INTERROMPIDO: só 'Retomar' + aviso de interrupção", () => {
    renderComp({ estado: estadoBase("interrompido") })
    expect(screen.getByText("Interrompido")).toBeInTheDocument()
    expect(screen.getByText(/foi interrompida/)).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retomar" })).toBeInTheDocument()
  })

  it("CONCLUÍDO: badge e 'Sincronizar de novo'", () => {
    renderComp({ estado: estadoBase("concluido") })
    expect(screen.getByText("Concluído")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sincronizar de novo" })).toBeInTheDocument()
  })

  it("PARCIAL: mostra a mensagem de erro e permite sincronizar de novo", () => {
    renderComp({ estado: estadoBase("parcial", { mensagem_erro: "falha X" }) })
    expect(screen.getByText("falha X")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sincronizar de novo" })).toBeInTheDocument()
  })

  it("mostra o erro da API quando pausar falha", () => {
    vi.mocked(hooks.usePausarCadastroTiny).mockReturnValue(
      mutacao(pausarMutate, { isError: true, error: new ApiError(409, "Não há sincronização em andamento.") }),
    )
    renderComp({ estado: estadoBase("sincronizando") })
    expect(screen.getByText("Não há sincronização em andamento.")).toBeInTheDocument()
  })

  it("abrir o diálogo de iniciar busca a estimativa e permite confirmar", async () => {
    vi.mocked(hooks.useCadastroTinyPreview).mockReturnValue({
      data: {
        fornecedor: "xbz",
        elegiveis: 1234,
        bloqueadas_local: 3,
        ja_cadastradas: 10,
        sem_estoque: 0,
        descontinuadas: 0,
        total_espelho: 1247,
        pronta_para_cadastro: true,
        motivo_nao_pronta: "",
        sincronizacao_em_andamento: false,
      },
      isLoading: false,
      isError: false,
    } as never)
    cadastrarMutateAsync.mockResolvedValue({ execucao_id: 7, status: "rodando" })
    renderComp({ estado: estadoBase("pronto") })

    fireEvent.click(screen.getByRole("button", { name: "Sincronizar com Tiny" }))
    expect(await screen.findByText("Sincronizar XBZ com o Tiny")).toBeInTheDocument()
    expect(screen.getByText("1.234")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Confirmar e iniciar" }))
    await waitFor(() => expect(cadastrarMutateAsync).toHaveBeenCalledTimes(1))
    expect(await screen.findByText(/Sincronização iniciada/)).toBeInTheDocument()
  })
})
