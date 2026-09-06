/**
 * Aliases de conveniência sobre os tipos gerados em schema.ts (a partir do
 * schema OpenAPI real do backend — ver `npm run generate:types`). Nunca
 * editar schema.ts à mão; para adicionar um tipo novo, gere de novo depois
 * de o backend expor o campo/endpoint.
 */
import type { components } from "./schema";

export type Instancia = components["schemas"]["Instancia"];
export type InstanciaDetalhe = components["schemas"]["InstanciaDetalhe"];
export type InstanciaListagem = components["schemas"]["InstanciaListagem"];
export type PaginatedInstanciaListagem = components["schemas"]["PaginatedInstanciaListagemList"];
export type PatchedInstancia = components["schemas"]["PatchedInstancia"];
export type StatusInstancia = components["schemas"]["StatusEnum"];
export type StatusExecucao = components["schemas"]["StatusExecucaoEnum"];
export type FornecedorEnum = components["schemas"]["FornecedorEnum"];
export type CorFornecedor = components["schemas"]["CorFornecedorEnum"];
export type FornecedorDetalhe = components["schemas"]["FornecedorDetalhe"];
export type ProdutosDetalheContagem = components["schemas"]["ProdutosDetalheContagem"];
export type ExecucaoResumida = components["schemas"]["ExecucaoResumida"];

export type VariacaoEspelho = components["schemas"]["VariacaoEspelho"];
export type PaginatedVariacaoEspelhoList = components["schemas"]["PaginatedVariacaoEspelhoList"];
export type StatusVariacao = components["schemas"]["StatusVariacaoEnum"];

export type ConfiguracoesInstancia = components["schemas"]["ConfiguracoesInstancia"];
export type PatchedConfiguracoesInstancia = components["schemas"]["PatchedConfiguracoesInstancia"];

export type Execucao = components["schemas"]["Execucao"];
export type PaginatedExecucaoList = components["schemas"]["PaginatedExecucaoList"];
export type TipoExecucao = components["schemas"]["TipoExecucaoEnum"];
export type LogItem = components["schemas"]["LogItem"];
export type PaginatedLogItemList = components["schemas"]["PaginatedLogItemList"];
export type NivelLog = components["schemas"]["NivelLogEnum"];

export type CredencialFornecedorResposta = components["schemas"]["CredencialFornecedorResposta"];
export type CredencialFornecedorEntrada = components["schemas"]["CredencialFornecedorEntrada"];
export type CadenciaFornecedor = components["schemas"]["CadenciaFornecedor"];
export type PatchedCadenciaFornecedor = components["schemas"]["PatchedCadenciaFornecedor"];
export type SincronizarResposta = components["schemas"]["SincronizarResposta"];
export type AutorizarResposta = components["schemas"]["AutorizarResposta"];

export type LoginRequest = components["schemas"]["LoginRequest"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type MeResponse = components["schemas"]["MeResponse"];
export type ErrorResponse = components["schemas"]["ErrorResponse"];

export type Resumo = components["schemas"]["Resumo"];
export type Periodo = components["schemas"]["PeriodoEnum"];
export type Alerta = components["schemas"]["Alerta"];
export type ExecucaoAtividade = components["schemas"]["ExecucaoAtividade"];
