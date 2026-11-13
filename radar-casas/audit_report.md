# Auditoria de fontes — Radar de Imóveis CABA

**Data:** 12/11/2026. **Escopo:** 73 imobiliárias cadastradas. **Filtros do usuário:** ignorados nesta auditoria.

Esta auditoria testa acesso ao site, descoberta de links e leitura de uma amostra de fichas, com uma segunda tentativa por navegador Chromium para os casos não confirmados. **Uma ficha legível não comprova que todas as ofertas foram coletadas nem que a gravação em banco funcionou.** Falha de acesso não comprova ausência de imóveis.

## Ajustes após a auditoria (12/11/2026)

- As cinco fontes com fichas verificadas mas fora da coleta foram integradas ao coletor principal: Carro Propiedades, Enrique Cannone Propiedades, Jakim Propiedades, Pablo Saullo e Hijos e RE/MAX Fly Liniers. Testes específicos encontram links em todas elas.
- O coletor principal agora tem 62 nomes de fontes configurados; a cobertura de fontes permanece distinta da contagem de 73 imobiliárias cadastradas.
- Uma falha real de parsing foi corrigida: menu com a palavra "Alquiler" não pode converter em aluguel um anúncio marcado como **Venta USD**. O caso de Pablo Saullo retornava 2 falsos positivos; depois da correção, 0 na mesma amostra.
- Miniaturas de propriedades relacionadas do Pablo Saullo foram excluídas quando não correspondem ao imóvel da ficha.
- Os links oficiais de Fedele Inmobiliaria e Jorge Reale foram localizados; o coletor deixou de depender dos perfis Argenprop para essas duas fontes. O novo catálogo da Fedele ainda está pendente de validação.
- **Proppies é um portal, não uma imobiliária**: 91 anúncios do radar vêm de lá, associados a 49 nomes de anunciantes após limpeza de ruído de avaliações. Os cards diferenciam anunciante e plataforma; quando há site próprio registrado, incluem esse link. Não suprimimos supostas duplicatas sem confirmação da identidade do imóvel.
- **Ponto operacional resolvido em 13/11/2026:** a execução de 12/11 havia ocorrido apenas em dry-run por falta de credenciais. Agora o GitHub Actions envia uma identidade OIDC temporária assinada para a Edge Function `radar-github-ingest`, que verifica repositório, workflow, branch, assinatura e prazo de validade antes de gravar no Supabase. A chave de administração permanece dentro do Supabase; não há segredo de banco armazenado no GitHub. O [teste de gravação real](https://github.com/diasmf/marcelo/actions/runs/43420672855) atualizou 1 imóvel sem erros.
- **Coleta diária:** cinco grupos de fontes no workflow `radar-collector.yml`, com 62 imobiliárias e navegador para os sites que precisam de renderização. Horário programado: 10h37 UTC (07h37 Buenos Aires). A rotina não depende do computador pessoal ligado.
- **Limpeza conservadora diária:** os URLs de anúncios são verificados independentemente; apenas HTTP 404 ou 410 confirmado em dois dias distintos marca o imóvel como inativo. Falhas 403/429/5xx, timeouts e respostas incertas não removem imóveis. A base `radar_caba_source_health` conserva evidências, sem apagar favoritos/comentários. [Teste do endpoint e 9 verificações de estado concluídos](https://github.com/diasmf/marcelo/actions/runs/43421612762).
- **Limitações:** 11 das 73 imobiliárias ainda não estão integradas ao coletor principal (incluindo 4 sem site cadastrado); teste de uma ficha não demonstra cobertura integral. Anúncios retirados do catálogo mas mantidos no site com HTTP 200 não serão removidos automaticamente até haver evidência mais forte de indisponibilidade.

[Validação das cinco novas fontes](https://github.com/diasmf/marcelo/actions/runs/43341125973)

## Resumo

| Situação | Imobiliárias |
|---|---:|
| Ficha de imóvel legível (amostra) | 43 |
| Ficha encontrada, extração não confirmada | 7 |
| Links encontrados, fichas não acessíveis | 3 |
| Site abre, sem links detectados | 9 |
| Site indisponível/bloqueado no teste | 7 |
| Sem catálogo online cadastrado | 4 |
| **Total** | **73** |

**Fontes no coletor principal (13/11/2026):** 62. **Com site cadastrado, mas ausentes do coletor:** 7. **Com fichas legíveis, mas ausentes do coletor:** 0.

## Resultado individual

| Imobiliária | Site no coletor (13/11) | Links identificados* | Resultado |
|---|:---:|---:|---|
| [Acosta](https://www.acostainmobiliaria.com.ar/index) | Sim | 11 | Ficha de imóvel legível (amostra) |
| [Amalfitani Inmuebles](https://www.amalfitani.com.ar/) | Sim | 3 | Ficha encontrada, extração não confirmada |
| [AMI Propiedades](https://amipropiedades.com.ar/) | Sim | 7 | Ficha de imóvel legível (amostra) |
| Barbarello Propiedades | Não | 0 | Sem catálogo online cadastrado |
| [Bener](https://www.bener.com.ar/) | Sim | 22 | Ficha de imóvel legível (amostra) |
| [Bigi Propiedades](https://bigiprop.com.ar/) | Não | 0 | Site abre, sem links detectados |
| [Borrajo](https://www.borrajopropiedades.com.ar/) | Sim | 22 | Ficha de imóvel legível (amostra) |
| [Bosich](https://www.bosichbienesraices.com.ar/) | Sim | 16 | Ficha encontrada, extração não confirmada |
| [Braña Inmobiliaria](https://xn--abraa-rta.com.ar/) | Sim | 0 | Site abre, sem links detectados |
| [Cantale Propiedades](https://www.cantalepropiedades.com.ar/propiedades) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Carballes Propiedades](https://www.carballesinmuebles.com.ar/) | Não | 4 | Ficha encontrada, extração não confirmada |
| [Carro Propiedades](https://carropropiedades.com.ar/properties) | Sim | 9 | Ficha de imóvel legível (amostra) |
| Cicchitti Hijo | Não | 0 | Sem catálogo online cadastrado |
| [Ciudad Inmobiliaria](https://ciudad-inmobiliaria.com/) | Não | 1 | Ficha encontrada, extração não confirmada |
| [CLOM](https://www.clompropiedades.com.ar/) | Sim | 20 | Ficha de imóvel legível (amostra) |
| [Crivez Silvana](https://www.crivezsilvana-propiedades.com.ar/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [D’Amato Propiedades](https://www.damatopropiedades.com.ar/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [D'AR Propiedades](https://dar-propiedades.com.ar/) | Não | 0 | Site abre, sem links detectados |
| [Dicons Propiedades](https://www.diconspropiedades.com/Alquiler) | Sim | 20 | Ficha de imóvel legível (amostra) |
| [El Altillo Inmuebles](https://www.elaltilloinmuebles.com.ar/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Enrique Cannone Propiedades](https://www.cannonepropiedades.com.ar/index.php) | Sim | 8 | Ficha de imóvel legível (amostra) |
| [Fedele Inmobiliaria](https://www.argenprop.com/inmobiliarias/fedele-inmobiliaria/ph) | Sim | 0 | Site indisponível/bloqueado no teste |
| Fincas Reguel | Não | 0 | Sem catálogo online cadastrado |
| [FJ Lujan Propiedades](https://www.fjlujan.com.ar/Alquiler) | Sim | 17 | Ficha de imóvel legível (amostra) |
| [Florencio González](https://florenciogonzalez.com.ar/) | Sim | 10 | Ficha de imóvel legível (amostra) |
| [Florencio Gonzalez Inmuebles](https://florenciogonzalez.com.ar/) | Sim | 10 | Ficha de imóvel legível (amostra) |
| [Furia Propiedades](https://www.furiapropiedades.com.ar/) | Sim | 5 | Ficha de imóvel legível (amostra) |
| [Gabriel Figueroa](https://gabrielfigueroa.com.ar/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Gamez Propiedades](https://www.gamezpropiedades.com.ar/) | Sim | 16 | Ficha de imóvel legível (amostra) |
| [Gentile Inmuebles](https://gentileinmuebles.com/) | Sim | 2 | Ficha encontrada, extração não confirmada |
| [Giacoletto](https://www.giacolettopropiedades.com/) | Sim | 20 | Ficha de imóvel legível (amostra) |
| [Golden Haus Luro](https://www.goldenhaus.com.ar/inmobiliaria/) | Sim | 14 | Ficha de imóvel legível (amostra) |
| [Grillo e Hijos](https://inmobiliariagrillo.com.ar/) | Sim | 23 | Ficha de imóvel legível (amostra) |
| [Gustavo Vega Propiedades](https://gustavovegapropiedades.com.ar/) | Sim | 0 | Site abre, sem links detectados |
| [Heiber Osornio](https://www.estudioheiberosornio.com/PHs) | Sim | 10 | Ficha de imóvel legível (amostra) |
| [Horacio Malito Propiedades](https://www.horaciomalitopropiedades.com.ar/) | Não | 0 | Site indisponível/bloqueado no teste |
| [Ing. E. A. Villamil Propiedades](https://www.ingenierovillamil.com.ar/) | Sim | 16 | Ficha encontrada, extração não confirmada |
| [Inmobiliaria Falco](https://www.inmofalco.com.ar/) | Sim | 0 | Site indisponível/bloqueado no teste |
| [Inmobiliaria Monferini SRL](https://monferinisrl.com.ar/) | Sim | 5 | Ficha de imóvel legível (amostra) |
| [Jakim Propiedades](https://www.jakimpropiedades.com/) | Sim | 6 | Ficha de imóvel legível (amostra) |
| [Jorge Parajon Propiedades](https://www.parajonpropiedades.com.ar/) | Sim | 0 | Site indisponível/bloqueado no teste |
| [Jorge Reale](https://jorgereale.com/) | Sim | 0 | Site indisponível/bloqueado no teste |
| [Jose Pintimalli Propiedades](https://www.josepintimalli.com.ar/Buscar) | Sim | 31 | Ficha de imóvel legível (amostra) |
| [Leonela Cullari Propiedades](https://www.leonelacullaripropiedades.com/) | Sim | 22 | Ficha de imóvel legível (amostra) |
| [Liotto Propiedades](https://liottopropiedades.com.ar/) | Sim | 11 | Links encontrados, fichas não acessíveis |
| [Maccaroni](https://maccaroni.com.ar/) | Sim | 24 | Ficha de imóvel legível (amostra) |
| [Magnacca Patelli Propiedades](https://magnaccapatelli.com/) | Sim | 0 | Site abre, sem links detectados |
| [Maqueda Propiedades](https://www.maqueda.com.ar/propiedades) | Sim | 0 | Site indisponível/bloqueado no teste |
| [Mario Notti Propiedades](https://marionotti.com.ar/) | Sim | 11 | Ficha de imóvel legível (amostra) |
| [Martorell Propiedades](https://martorellprop.com.ar/) | Sim | 3 | Ficha de imóvel legível (amostra) |
| [Massaro Propiedades](https://massaropropiedades.com.ar/) | Sim | 0 | Site abre, sem links detectados |
| [MEL Propiedades](https://www.melpropiedades.com.ar/) | Não | 0 | Site abre, sem links detectados |
| [MG Bienes Raíces](https://bienesraicesmg.com.ar/) | Sim | 16 | Links encontrados, fichas não acessíveis |
| [Millán y Alessi](https://www.millanalessi.com.ar/) | Sim | 18 | Ficha de imóvel legível (amostra) |
| [Naccarato Propiedades](https://www.naccaratopropiedades.com.ar/propiedades/) | Sim | 4 | Ficha encontrada, extração não confirmada |
| [Nolé Propiedades](https://www.nolepropiedades.com.ar/) | Sim | 28 | Ficha de imóvel legível (amostra) |
| [Norde Propiedades](https://www.nordepropiedades.com.ar/) | Sim | 12 | Ficha de imóvel legível (amostra) |
| [Pablo Saullo e Hijos](https://pablosaulloehijos.com.ar/propiedades/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Paladino Negocios Inmobiliarios](https://www.paladinoprop.com.ar/estado/en-alquiler/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Pallarols Santander Propiedades](https://www.pallarols-santander.com/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Pignataro & Asociados](https://pignataroyasociados.com.ar/) | Não | 0 | Site abre, sem links detectados |
| [RE/MAX Fly Liniers](https://www.remax-fly.com.ar/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| [Ricardo López Propiedades](https://rlpropiedades.com.ar/propiedades/) | Sim | 32 | Ficha de imóvel legível (amostra) |
| Rocamora Inmobiliaria | Não | 0 | Sem catálogo online cadastrado |
| [Roman Propiedades](https://inmobiliariaroman.com.ar/) | Sim | 7 | Links encontrados, fichas não acessíveis |
| [SegurBA Propiedades](https://www.segurba.com.ar/) | Sim | 0 | Site abre, sem links detectados |
| [Tizado Villa Luro](https://www.tizado.com/) | Sim | 15 | Ficha de imóvel legível (amostra) |
| [Todoroff Propiedades](https://www.argenprop.com/inmobiliarias/todoroff-propiedades/inmuebles/mataderos) | Sim | 0 | Site indisponível/bloqueado no teste |
| [Varcasia Propiedades](https://www.varcasiapropiedades.com.ar/) | Sim | 37 | Ficha de imóvel legível (amostra) |
| [Varela Villalba](https://www.varelavillalba.com.ar/) | Sim | 20 | Ficha de imóvel legível (amostra) |
| [Vitale Feola Propiedades](https://vitalefeola.com.ar/) | Sim | 19 | Ficha de imóvel legível (amostra) |
| [Werba Inmuebles](https://www.werba.com.ar/) | Sim | 1 | Ficha de imóvel legível (amostra) |
| [Yacopino Inmobiliarias](https://www.yacopino.com.ar/busqueda-de-propiedades-en-alquiler) | Sim | 14 | Ficha de imóvel legível (amostra) |

*Contagem de links limitada pela amostragem e pelo método utilizado; não é um inventário completo.

## Próximas correções necessárias

- Habilitar no coletor principal as fontes que estão cadastradas, mas não participam da coleta.
- Corrigir sites que requerem navegador/iframe, e distinguir URLs de categorias de fichas individuais.
- Reavaliar fontes bloqueadas ou sem links antes de concluir que não possuem anúncios.
- Verificar gravação no banco e renovação diária separadamente: esta auditoria é somente leitura.

## Execuções técnicas

- [Auditoria HTTP inicial](https://github.com/diasmf/marcelo/actions/runs/43337868486)
- [Segunda auditoria Chromium](https://github.com/diasmf/marcelo/actions/runs/43338626396)
- [Dados brutos consolidados](https://github.com/diasmf/marcelo/blob/master/radar-casas/audit_final.json)
