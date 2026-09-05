# Este app não tem tabelas próprias: os endpoints de dashboard (resumo,
# alertas, atividade) leem e agregam dados de instancias/catalogo/
# sincronizacao. Alertas são sempre derivados do estado atual — nunca
# persistidos aqui (ver apps/dashboard/services.py).
