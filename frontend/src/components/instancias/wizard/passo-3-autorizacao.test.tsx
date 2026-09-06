import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Passo3Autorizacao } from "./passo-3-autorizacao";

const REDIRECT_URI = "https://sync-api.automasoluct.com.br/api/tiny/oauth/callback/loja-x";

function renderPasso(overrides: Partial<React.ComponentProps<typeof Passo3Autorizacao>> = {}) {
  const onAutorizar = vi.fn();
  const onVoltar = vi.fn();
  render(
    <Passo3Autorizacao
      redirectUri={REDIRECT_URI}
      status="nao_conectado"
      autorizacaoFalhou={false}
      isAutorizando={false}
      onVoltar={onVoltar}
      onAutorizar={onAutorizar}
      {...overrides}
    />
  );
  return { onAutorizar, onVoltar };
}

describe("Passo3Autorizacao", () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it("começa com o botão Autorizar no ERP desabilitado", () => {
    renderPasso();
    expect(screen.getByRole("button", { name: /Autorizar no ERP/ })).toBeDisabled();
  });

  it("só habilita o botão quando os 3 itens do checklist estão marcados", () => {
    renderPasso();
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes).toHaveLength(3);

    fireEvent.click(checkboxes[0]);
    fireEvent.click(checkboxes[1]);
    expect(screen.getByRole("button", { name: /Autorizar no ERP/ })).toBeDisabled();

    fireEvent.click(checkboxes[2]);
    expect(screen.getByRole("button", { name: /Autorizar no ERP/ })).toBeEnabled();
  });

  it("o botão Copiar chama navigator.clipboard.writeText com a redirect_uri exata", async () => {
    renderPasso();
    fireEvent.click(screen.getByRole("button", { name: "Copiar" }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(REDIRECT_URI);
  });

  it("clicar em Autorizar no ERP com o checklist completo chama onAutorizar", () => {
    const { onAutorizar } = renderPasso();
    screen.getAllByRole("checkbox").forEach((checkbox) => fireEvent.click(checkbox));
    fireEvent.click(screen.getByRole("button", { name: /Autorizar no ERP/ }));
    expect(onAutorizar).toHaveBeenCalledTimes(1);
  });

  it("mostra um banner de erro quando a autorização anterior falhou", () => {
    renderPasso({ autorizacaoFalhou: true });
    expect(screen.getByText(/A autorização não foi concluída/)).toBeInTheDocument();
  });
});
