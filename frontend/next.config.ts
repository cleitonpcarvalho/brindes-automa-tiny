import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Runtime enxuto para a imagem de produção (ver frontend/Dockerfile) —
  // copia só o necessário para rodar `node server.js`, sem node_modules inteiro.
  output: "standalone",
};

export default nextConfig;
