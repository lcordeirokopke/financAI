# Integração com Figma: post editável, não imagem fixa

## Resposta curta

Sim, é viável, e a restrição que parece bloquear o projeto não bloqueia **este** projeto.

A plataforma Figma não permite que um serviço de backend crie design no canvas sozinho, sem humano presente. Isso é fato apurado e está detalhado abaixo. Só que o modo de operação do Suno Content é estúdio editorial: o supervisor humano **já vai abrir o Figma** para revisar e editar a peça. Um caminho que exige um clique humano para disparar não custa nada, porque o humano já está lá.

O resultado entregue é o que foi pedido: frames Figma nativos, com camadas de texto, auto layout, componentes e variáveis reais. Não PNG. O humano edita o texto, troca a ordem dos slides, ajusta o gancho, e só então exporta.

Isto não é previsão: foi executado contra a conta real desta sessão, e o carrossel de cinco slides gerado a partir de um `CarrosselPayload` está descrito na seção de verificação empírica, com o link do arquivo.

---

## O eixo que decide o desenho: instanciar vs reconstruir

Antes de comparar rotas, a distinção que importa mais que grau de automação:

**Instanciar.** O carrossel da marca existe no Figma como componente publicado, com tipografia, logo, grid, cores e variáveis já resolvidos. O pipeline entrega só o conteúdo. O executor cria instâncias e preenche as camadas de texto. Nada é "desenhado" na hora.

**Reconstruir.** O executor recria as camadas a partir de outra representação (o HTML do dashboard, ou uma descrição em prosa). O resultado é editável, mas é um sósia do template da marca, não o template da marca.

**Recomendação: instanciar.** Três consequências diretas:

1. As limitações documentadas da escrita via MCP (sem suporte a imagens/assets, fontes customizadas problemáticas) mordem muito menos, porque o logo e a fonte vêm do componente, não da geração.
2. O não determinismo do agente sai do caminho crítico. O template é fixo; o que varia é texto que o pipeline já validou pela M2.
3. O executor fica trocável. A mesma template e o mesmo payload aceitam dois runners diferentes (rota A e rota B abaixo), o que protege a entrega se um deles esbarrar em plano ou seat.

---

## O que a plataforma permite hoje (apurado, set/2026)

### REST API: não muta canvas

A REST API é GET-only para conteúdo de arquivo e de nó. Ela **não cria nem modifica nós**. O que ela escreve é periferia: comentários, dev resources, webhooks e variables (e variables exige org no plano Enterprise, com escopo `file_variables:write`).

Consequência: não existe "POST /criar-frame". Qualquer rota de criação passa pela Plugin API, direta ou indiretamente.

### Plugin API: única via de mutação, roda no editor

A Plugin API cria e edita nós, instancia componentes, define `characters` em camadas de texto (depois de `figma.loadFontAsync`), seta variáveis e propriedades de componente. Plugin faz requisição de rede se o domínio estiver em `networkAccess.allowedDomains` no manifest.

Restrição estrutural: plugin não roda headless. Precisa de uma instância do Figma aberta. Times que quiseram automação contínua acabaram com uma máquina dedicada rodando o desktop app com o arquivo aberto, o que é gambiarra, não arquitetura.

Desenvolver plugin funciona em qualquer plano, importando o `manifest.json` pelo desktop app (Plugins > Development > Import plugin from manifest). **Publicar** plugin privado para a organização exige plano Organization ou Enterprise.

### MCP remoto: escrita no canvas desde fev/2026

O servidor MCP remoto (`mcp.figma.com/mcp`) ganhou escrita. O que interessa aqui:

- `use_figma`: executa JavaScript da Plugin API no contexto de um arquivo Figma, **remotamente, sem o arquivo precisar estar aberto no editor**. Cria e edita frames, componentes, auto layout, variáveis, e enxerga o design system existente. O alvo é indicado por URL do arquivo ou link para uma seleção, colado no prompt.
- `generate_figma_design` (code to canvas): captura UI viva rodando no browser (inclusive localhost) e converte em camadas de design editáveis.
- `create_new_file`, `upload_assets`, `generate_diagram`: criação de arquivo em drafts, upload de imagem (até 10MB), diagrama FigJam a partir de Mermaid.
- Leitura: `whoami` (devolve planos e tipos de seat), `get_design_context`, `get_variable_defs`, `search_design_system`, `download_assets`, entre outros.

Requisitos e limites declarados: **Full seat** para escrever em arquivo fora de drafts, mais permissão de edição naquele arquivo (Dev seat é read-only). Limite de 20kb de resposta por chamada. Sem suporte a assets, componentes que contenham imagem, e GIF. "Fontes customizadas não funcionam". A escrita depende de carregar a skill `figma-use` no cliente.

O plano educacional recebe as funcionalidades do Professional, e a Figma equiparou o limite de MCP da Education ao Professional: 200 chamadas de ferramenta por dia, 10 por minuto para seats Dev e Full.

### O que está fechado: backend autônomo

O acesso ao MCP é restrito por desenho: allowlist de clientes aprovados (IDEs e agentes como Claude Code, Cursor, VS Code, Codex), escopo `mcp:connect` indisponível para OAuth app próprio, dynamic client registration recusado, personal access token rejeitado no endpoint MCP, e nenhum fluxo de autenticação headless.

Somando com a REST API que não muta canvas: **um serviço de backend do Suno Content não consegue, hoje, criar design no Figma sem humano no circuito.** Declarar isso explicitamente evita que alguém desenhe o E8 apontando para essa porta.

Alternativa que tem API de verdade para essa forma: a **Canva Connect API** tem Autofill, que aplica um brand template a partir de dados e devolve um design editável no Canva, chamável de backend. Está atrás de organização Canva Enterprise (planos pagos têm trial limitado enquanto a integração está em desenvolvimento). Se em algum momento a exigência "sem humano no disparo" virar requisito duro, o caminho é esse, não o Figma.

---

## Rotas, em ordem de recomendação

### Rota A: `use_figma` a partir do Claude Code, preenchendo template componentizado

O pipeline persiste a `Peca` com `CarrosselPayload`. O agente recebe a URL do arquivo Figma e o payload, e executa código de Plugin API via `use_figma` que instancia o componente por slide e preenche as camadas de texto.

- **A favor:** zero infraestrutura nova, o arquivo não precisa estar aberto, o agente enxerga componentes e variáveis do design system, escrita em arquivo existente.
- **Contra:** exige Full seat em plano pago; o runtime remoto só enxerga o catálogo Google Fonts, então tipografia licenciada da marca não carrega; imagens não entram pela escrita; 20kb de resposta por chamada obriga a fatiar as 9 células; disparo é no IDE, não no dashboard.
- **Quando é a certa:** existe Full seat e a tipografia da marca é fonte Google. **Verificado nesta conta: o seat é Full e a rota está liberada** (ver a seção de verificação empírica).

### Rota B: plugin próprio de desenvolvimento local, que busca JSON da API do pipeline

Um plugin pequeno, importado por manifest no desktop app. Ele chama `GET /pecas/{documento_id}` na API do pipeline (domínio declarado em `networkAccess`), lista as 9 células, e o humano escolhe qual materializar. O plugin instancia o template e preenche.

- **A favor:** roda em qualquer plano; roda no editor de verdade, onde a fonte da marca está carregada e imagens funcionam; determinístico, porque é código nosso, não geração; reprodutível por terceiros, o que serve ao Entregável 6; o humano já está no Figma, então o clique é grátis.
- **Contra:** exige escrever e manter o plugin (uma tarde de trabalho, não mais); desktop app obrigatório; publicar como plugin privado da org exige plano Organization, mas para a demo o import por manifest resolve.
- **Quando é a certa:** se o seat não permitir `use_figma`, ou se o teste de fonte da marca falhar. E é a rota mais defensável em entrega avaliada, por ser determinística.

### Rota C: code to canvas a partir do preview do dashboard

O dashboard do E8 já vai renderizar o carrossel em HTML. `generate_figma_design` captura essa UI e devolve camadas editáveis.

- **A favor:** reaproveita o que o E8 já tem; qualquer seat captura para drafts.
- **Contra:** é reconstrução, não instanciação. Sai um sósia do post, não o template da marca, sem componentes nem variáveis da biblioteca.
- **Quando é a certa:** como atalho de demonstração, ou se o template da marca ainda não existir no Figma.

### Rota D: Figma Buzz, bulk create por planilha

Buzz cria vários assets de uma vez a partir de CSV/XLSX: cada coluna é um campo, cada linha é um asset. O pipeline exporta um CSV com as 9 células, o humano sobe no template Buzz e gera.

- **A favor:** zero código. Feito exatamente para peça de social em volume.
- **Contra:** upload manual, sem API. O ganho de automação é parcial e o passo humano é burocrático, não editorial.
- **Quando é a certa:** validação rápida do template antes de investir em A ou B.

### Rota E: plugin de terceiros com planilha

Plugins como Google Sheets Sync, Sheets to Layers, SheetSync e data.to.design preenchem camadas nomeadas com `#coluna` a partir de Sheets, CSV ou JSON. O pipeline escreve na planilha, o humano roda o plugin.

- **A favor:** nenhum código de plugin para manter.
- **Contra:** dependência de terceiro no caminho da entrega, e convenção de nomeação de camada imposta de fora.
- **Quando é a certa:** protótipo, ou se ninguém quiser tocar em código de plugin.

---

## O contrato já existe: `CarrosselPayload` como contrato de preenchimento

Nada de formato novo. O que a arquitetura já define serve direto:

```
Slide.papel  ("gancho" | "corpo" | "conclusao")  ->  variante do componente de slide
Slide.texto                                      ->  camada de texto nomeada (#texto)
Slide.claim_ids                                  ->  pluginData no nó, para rastreabilidade
Peca.celula_id ("iniciante__carrossel")          ->  nome do frame raiz
Peca.tentativa                                   ->  sufixo de versão no nome do frame
```

Três coisas que isso compra de graça:

1. O limite de 220 caracteres por slide já é validado pela M2 antes de chegar ao Figma. O template não precisa lidar com overflow imprevisto, e um estouro de caixa passa a ser bug de template, não de conteúdo.
2. `papel` mapeado para variante é o que faz gancho, corpo e conclusão terem layout diferente sem lógica no executor.
3. `claim_ids` gravado como `sharedPluginData` no nó mantém a rastreabilidade do Entregável 4 **dentro** do arquivo Figma, e não só no dashboard. Atenção: `setPluginData` **não funciona** pelo MCP remoto (erro "not supported in this host runtime, only private plugins on web can use it"). O substituto é `setSharedPluginData("suno.content", chave, valor)`, com namespace fixo. Testado e funcionando.

Uma convenção de nomeação de camada precisa ser fixada no template e documentada, porque as rotas B e E dependem dela literalmente.

---

## Fechando o loop: o caminho de volta é automatizável

A escrita é restrita, a leitura não é. Depois que o humano editou:

- `GET /v1/images/{key}` com node ids e `format` devolve PNG, JPG, SVG ou PDF renderizados pela CDN do Figma (URLs expiram em 30 dias, até 32 megapixels). Funciona de backend, com token, sem humano.
- Webhooks com contexto de arquivo ou projeto disparam em `FILE_UPDATE`, `FILE_COMMENT` e `FILE_VERSION_UPDATE`. Dá para o pipeline saber que a peça foi tocada.
- `GET /v1/files/{key}` relê o texto final, o que permite comparar o que o pipeline gerou com o que o humano publicou.
- Plan access tokens da REST API são escopados à organização, expiram em até um ano e aceitam allowlist de recursos, ou seja, servem a automação headless não atrelada a uma pessoa.

Isso ataca diretamente a **Lacuna conhecida 5** de `docs/arquiteturas.md`: hoje ninguém mede concordância entre "o avaliador aprovou" e "o humano publicou". Reler o frame editado e diffar contra o `CarrosselPayload` original transforma essa lacuna em métrica. O quanto o humano precisou reescrever é a validação externa do avaliador, e vale mais que qualquer métrica interna.

---

## Onde isso encaixa na arquitetura

Camada de renderização pendurada no E8, consumindo `Peca` já aprovada. **Não toca E1 a E7.** O grafo, o avaliador e o refinement loop ficam intactos, e é isso que torna seguro adicionar isso agora: se a integração com Figma falhar, o pipeline continua entregando as 9 células.

Efeito nos entregáveis: reforça o 4 (interface com rastreabilidade, porque a rastreabilidade passa a existir dentro do Figma) e o 5 (vídeo demonstrativo, porque "o post nasce editável e o supervisor edita ao vivo" é uma cena de demo muito melhor que um PNG na tela).

Não muda o escopo declarado: publicação automática em rede social continua fora.

---

## Verificação empírica (feita, não presumida)

Tudo abaixo foi executado contra a conta real, em arquivo de rascunho, via MCP remoto.

**Conta.** `whoami` devolve plano educacional (`tier: student`), **seat Full**, papel admin no time. Full seat é exatamente o requisito da escrita via `use_figma`. A Figma equiparou o limite de MCP da Education ao Professional: 200 chamadas por dia, 10 por minuto. A rota A está liberada.

**Fontes: a limitação é real, e é mais específica do que a documentação diz.** O runtime remoto expõe 1938 famílias, que são o catálogo Google Fonts mais os padrões da Figma. `Inter` e `Montserrat` carregam e aceitam `characters` sem problema. Já `Graphik`, `Helvetica Neue` e `Proxima Nova` não existem no runtime, e `loadFontAsync` falha com "The font family does not exist".

A consequência prática é esta: **se a tipografia da marca for uma fonte Google, a rota A funciona inteira.** Se for uma fonte licenciada ou proprietária, ela precisa estar carregada no ambiente, e fonte enviada para a Figma exige plano Organization. Nesse cenário a rota B ganha, porque o plugin roda no editor de verdade, onde a fonte instalada na máquina está disponível.

**Rastreabilidade.** `setPluginData` é bloqueado no runtime remoto. `setSharedPluginData` funciona e é o caminho correto.

**Fluxo completo, provado.** Em uma única chamada foi possível: criar uma coleção de variáveis com `cor/fundo`, `cor/texto` e `cor/destaque` com scopes explícitos; montar um component set `slide-carrossel` com três variantes de `papel` (gancho, corpo, conclusão), cada uma com auto layout, 1080x1350, fills vinculados a variáveis e uma camada de texto nomeada `#texto`; instanciar cinco slides a partir de um `CarrosselPayload` de exemplo do Copom; preencher o texto de cada um; gravar `claim_ids` e `celula_id` em `sharedPluginData` por instância; e tirar screenshot do resultado.

Saiu um carrossel nativo, editável, com componentes e variáveis reais. Trocar o texto de um slide no editor é clicar e digitar. Trocar a cor de fundo dos nove é mudar uma variável. **A pergunta original está respondida com evidência: não é imagem fixa.**

Arquivo de teste: `https://www.figma.com/design/hplTdfmdwkQbNB8FujS3FH`

Dois detalhes de implementação que custaram uma tentativa e ficam registrados:

- `layoutSizingHorizontal = "FILL"` só vale para filho de frame com auto layout. Criar o frame e depois embrulhar com `figma.createComponentFromNode(frame)` funciona; appendar o frame dentro de um `createComponent()` vazio não.
- A cada chamada o contexto volta para a primeira página, e nenhum estado de JavaScript sobrevive entre chamadas. IDs precisam ser devolvidos e repassados como literais.
- O teste instanciou de `defaultVariant` e trocou a variante depois com `setProperties`. Funcionou com uma camada de texto, mas herança de override na troca de variante é o modo de falha esperado quando o template ganhar mais camadas. Instanciar direto da variante certa é o padrão seguro.

## Riscos restantes, com mitigação

- **Tipografia da marca**: confirmar se é fonte Google. Se não for, rota B.
- **20kb de resposta por chamada** no `use_figma`: fatiar por célula, nunca as 9 de uma vez.
- **Imagens e assets** não são suportados na escrita via MCP. Logo, gráfico e foto precisam já existir dentro do componente, ou entrar por `upload_assets`.
- **Não determinismo do agente**: o template carrega o desenho e o executor só preenche. A instrução é "instancie e preencha", nunca "desenhe um post".
- **Cota de 200 chamadas por dia**: suficiente com folga para 9 células por documento, mas não para loop de tentativa e erro descuidado.
- **Publicação de plugin privado exige plano Organization**: se a rota B for escolhida, na demo o import por manifest no desktop app resolve.

## Próximo passo, já que o template não existe

A ordem muda, mas o template não é um projeto à parte: o próprio `use_figma` já gerou um esqueleto funcional dele no teste.

1. **Gerar o esqueleto do template pela rota A**, revisar no editor e ajustar à mão o que for decisão de marca: grade 1080x1350, variantes por `papel`, cores e tipografia em variáveis, logo como elemento fixo do componente. Publicar como biblioteca quando estabilizar.
2. **Fixar a convenção de nomeação** de camada, que é contrato entre pipeline e arquivo Figma.
3. **Um documento real ponta a ponta**: `CarrosselPayload` aprovado pelo avaliador virando carrossel instanciado.
4. **Só então decidir o disparo**: agente pelo Claude Code (rota A) ou plugin próprio no editor (rota B). As duas consomem exatamente o mesmo template e o mesmo payload, então essa decisão pode ficar para depois sem travar nada.

A única pergunta aberta é a tipografia. A home da suno.com.br não expõe a fonte de marca no HTML estático (só o fallback `Arial, Helvetica, sans-serif`), e a fonte do site não é necessariamente a do kit de social. Quem mantém o kit de marca responde isso em uma linha, e a resposta decide se a rota A é incondicional ou se a rota B entra no lugar.

---

## Fontes

- [Figma REST API: variables endpoints](https://developers.figma.com/docs/rest-api/variables-endpoints)
- [Figma REST API: file endpoints](https://developers.figma.com/docs/rest-api/file-endpoints/)
- [Figma MCP server: write to canvas](https://developers.figma.com/docs/figma-mcp-server/write-to-canvas)
- [Figma MCP server: code to canvas](https://developers.figma.com/docs/figma-mcp-server/code-to-canvas/)
- [Figma MCP server: tools and prompts](https://developers.figma.com/docs/figma-mcp-server/tools-and-prompts/)
- [Figma skills for MCP](https://help.figma.com/hc/en-us/articles/39166810751895-Figma-skills-for-MCP)
- [Claude Code and Figma: set up the MCP server](https://help.figma.com/hc/en-us/articles/39888612464151-Claude-Code-and-Figma-Set-up-the-MCP-server)
- [Figma Plugins: making network requests](https://developers.figma.com/docs/plugins/making-network-requests)
- [Figma Plugins: manifest](https://developers.figma.com/docs/plugins/manifest)
- [Create a classic plugin for development](https://help.figma.com/hc/en-us/articles/360042786733-Create-a-classic-plugin-for-development)
- [Create private plugins for an organization](https://help.figma.com/hc/en-us/articles/4404228629655-Create-private-organization-plugins)
- [Bulk create assets in Figma Buzz](https://help.figma.com/hc/en-us/articles/31271824185623-Bulk-create-assets-in-Figma-Buzz)
- [Figma MCP vs Figma API for AI agents (Scalekit)](https://www.scalekit.com/blog/figma-mcp-vs-api)
- [Figma's MCP just gave AI agents write access (Bitovi)](https://www.bitovi.com/blog/figma-just-opened-the-canvas-to-agents.-heres-what-actually-happens)
- [Canva Connect API: autofill](https://www.canva.dev/docs/connect/api-reference/autofills/)
- [Google Sheets Sync (Figma Community)](https://www.figma.com/community/plugin/735770583268406934/google-sheets-sync)
- [Limites de MCP no plano educacional (Figma Forum)](https://forum.figma.com/report-a-problem-6/mcp-limit-education-plan-55485)
- [Figma for Education 2026](https://aitoolpick.org/blog/figma-for-education-2026/)
- [Adicionar uma fonte à Figma](https://help.figma.com/hc/articles/360039956894-Add-a-font-to-Figma)
