# Agenda de Estudos - ADS UNIFOR

Projeto inicial pra organizar as matérias do semestre. Fiz em React pra praticar o básico de componentes e como o estado do sistema funciona na prática.

### O que o app faz:
- Adiciona matéria (limpando espaços vazios com .trim())
- Marca como concluída (clicando no texto)
- Deleta o que não serve mais
- **Dark Mode:** Deixei o visual minimalista e escuro pra não cansar a vista estudando.

### O que eu aprendi fazendo:
O foco aqui foi entender como o React lida com a lista de tarefas. Em vez de só mudar a variável, usei a forma funcional do `useState` (ex: `setLista(prev => ...)`). Isso é importante pra garantir que o React não se perca quando a gente adiciona itens rápido demais.

Também troquei o evento de teclado pro `onKeyDown`, que é o padrão mais atual, e foquei em manter o código limpo, sem bibliotecas externas pesadas.

### Como rodar:
1. `npm install`
2. `npm run dev`
