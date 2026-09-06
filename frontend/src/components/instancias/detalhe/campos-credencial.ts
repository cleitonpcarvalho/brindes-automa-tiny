import type { FornecedorEnum } from "@/lib/api/types"

export interface CampoCredencial {
  chave: string
  rotulo: string
  obrigatorio: boolean
  sensivel: boolean
}

/**
 * Espelha `CAMPOS_POR_FORNECEDOR` do backend (apps/instancias/constants.py) —
 * só o suficiente para montar o formulário (rótulo, obrigatoriedade,
 * sensibilidade). Mantenha os dois em sincronia se um fornecedor mudar.
 */
export const CAMPOS_CREDENCIAL: Record<FornecedorEnum, CampoCredencial[]> = {
  xbz: [
    { chave: "cnpj", rotulo: "CNPJ", obrigatorio: true, sensivel: false },
    { chave: "token", rotulo: "Token", obrigatorio: true, sensivel: true },
  ],
  asia: [
    { chave: "api_key", rotulo: "API Key", obrigatorio: true, sensivel: true },
    { chave: "secret_key", rotulo: "Secret Key", obrigatorio: true, sensivel: true },
  ],
  somarcas: [
    { chave: "usuario", rotulo: "Usuário", obrigatorio: true, sensivel: false },
    { chave: "senha", rotulo: "Senha", obrigatorio: true, sensivel: true },
    { chave: "estado", rotulo: "Estado (opcional)", obrigatorio: false, sensivel: false },
  ],
  spot: [{ chave: "access_key", rotulo: "Access Key", obrigatorio: true, sensivel: true }],
}
