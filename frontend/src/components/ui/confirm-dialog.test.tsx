import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "./confirm-dialog";

describe("ConfirmDialog", () => {
  it("não chama onConfirm só de abrir o dialog", async () => {
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        trigger={<Button>Desconectar</Button>}
        title="Desconectar instância"
        description="Os tokens serão apagados."
        confirmLabel="Desconectar"
        onConfirm={onConfirm}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    expect(await screen.findByText("Os tokens serão apagados.")).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("só chama onConfirm depois do clique no botão de confirmação", async () => {
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        trigger={<Button>Desconectar</Button>}
        title="Desconectar instância"
        description="Os tokens serão apagados."
        confirmLabel="Desconectar"
        onConfirm={onConfirm}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    const botoesConfirmar = await screen.findAllByRole("button", { name: "Desconectar" });
    // o segundo é o botão de confirmação dentro do dialog (o primeiro é o trigger)
    fireEvent.click(botoesConfirmar[botoesConfirmar.length - 1]);

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("cancelar fecha o dialog sem chamar onConfirm", async () => {
    const onConfirm = vi.fn();

    render(
      <ConfirmDialog
        trigger={<Button>Desconectar</Button>}
        title="Desconectar instância"
        description="Os tokens serão apagados."
        confirmLabel="Desconectar"
        onConfirm={onConfirm}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Desconectar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));

    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.queryByText("Os tokens serão apagados.")).not.toBeInTheDocument();
  });
});
