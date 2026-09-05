/**
 * Aliases de conveniência sobre os tipos gerados em schema.ts (a partir do
 * schema OpenAPI real do backend — ver `npm run generate:types`). Nunca
 * editar schema.ts à mão; para adicionar um tipo novo, gere de novo depois
 * de o backend expor o campo/endpoint.
 */
import type { components } from "./schema";

export type Instancia = components["schemas"]["Instancia"];
export type InstanciaListagem = components["schemas"]["InstanciaListagem"];
export type PaginatedInstanciaListagem = components["schemas"]["PaginatedInstanciaListagemList"];
export type PatchedInstancia = components["schemas"]["PatchedInstancia"];
export type StatusInstancia = components["schemas"]["StatusEnum"];
export type FornecedorEnum = components["schemas"]["FornecedorEnum"];
export type CorFornecedor = components["schemas"]["CorFornecedorEnum"];

export type LoginRequest = components["schemas"]["LoginRequest"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type MeResponse = components["schemas"]["MeResponse"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];

export type Resumo = components["schemas"]["Resumo"];
export type Periodo = components["schemas"]["PeriodoEnum"];
export type Alerta = components["schemas"]["Alerta"];
export type ExecucaoAtividade = components["schemas"]["ExecucaoAtividade"];
