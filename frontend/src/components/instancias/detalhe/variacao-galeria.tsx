"use client"

import { useState } from "react"
import { ImageOff } from "lucide-react"
import { cn } from "cn"

interface Props {
  imagens: string[]
  alt: string
}

function Fallback({ texto }: { texto: string }) {
  return (
    <div className="flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-muted/40 text-muted-foreground">
      <ImageOff size={28} />
      <span className="text-caption-label">{texto}</span>
    </div>
  )
}

/**
 * Galeria somente leitura: imagem principal grande (proporção preservada,
 * nunca distorcida — `object-contain` num quadro fixo) e miniaturas para as
 * demais. Sem imagem no espelho, ou URL quebrada, cai num placeholder
 * discreto. As URLs são de CDN dos fornecedores (externas), por isso `<img>`
 * puro e não `next/image` (sem `remotePatterns` configurado no projeto).
 */
export function VariacaoGaleria({ imagens, alt }: Props) {
  const [indice, setIndice] = useState(0)
  const [quebradas, setQuebradas] = useState<Set<string>>(new Set())

  if (imagens.length === 0) {
    return <Fallback texto="Sem imagem no espelho" />
  }

  const atual = imagens[Math.min(indice, imagens.length - 1)]
  const marcarQuebrada = (url: string) =>
    setQuebradas((anterior) => new Set(anterior).add(url))

  return (
    <div className="flex flex-col gap-3">
      {quebradas.has(atual) ? (
        <Fallback texto="Imagem indisponível" />
      ) : (
        <div className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-xl border border-border bg-card">
          {/* eslint-disable-next-line @next/next/no-img-element -- URL externa de CDN do fornecedor */}
          <img
            src={atual}
            alt={alt}
            loading="lazy"
            onError={() => marcarQuebrada(atual)}
            className="max-h-full max-w-full object-contain"
          />
        </div>
      )}

      {imagens.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {imagens.map((url, i) => (
            <button
              key={`${url}-${i}`}
              type="button"
              onClick={() => setIndice(i)}
              aria-label={`Ver imagem ${i + 1} de ${imagens.length}`}
              aria-current={i === indice}
              className={cn(
                "flex size-14 items-center justify-center overflow-hidden rounded-lg border bg-card transition-colors",
                i === indice
                  ? "border-primary ring-1 ring-primary"
                  : "border-border hover:border-border-hover",
              )}
            >
              {quebradas.has(url) ? (
                <ImageOff size={16} className="text-muted-foreground" />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element -- URL externa de CDN do fornecedor
                <img
                  src={url}
                  alt=""
                  loading="lazy"
                  onError={() => marcarQuebrada(url)}
                  className="max-h-full max-w-full object-contain"
                />
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
