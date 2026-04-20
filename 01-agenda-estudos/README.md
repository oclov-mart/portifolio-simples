# Lista de Tarefas de Faculdade

Um projeto simples em React para gerenciar tarefas de estudos, ideal para portfólio de estudante de primeiro semestre.

## 📋 Descrição

Aplicação web simples para organizar matérias e tarefas de faculdade. Desenvolvida com React e Vite, utilizando apenas CSS puro para estilização.

## 🚀 Funcionalidades

- ✅ Adicionar novas tarefas/matérias
- ✅ Marcar tarefas como concluídas (clicando no texto)
- ✅ Excluir tarefas individualmente
- ✅ Interface simples e organizada

## 🛠️ Tecnologias Utilizadas

- **React 18** - Biblioteca JavaScript para criar interfaces
- **Vite** - Ferramenta de build rápida
- **CSS Puro** - Estilização sem bibliotecas externas

## 📁 Estrutura do Projeto

```
lista-tarefas-faculdade/
├── src/
│   ├── App.jsx          # Componente principal com toda a lógica
│   ├── App.css          # Estilos da aplicação
│   ├── main.jsx         # Ponto de entrada do React
│   └── index.css        # Estilos globais
├── index.html           # Template HTML
├── package.json         # Dependências do projeto
└── vite.config.js       # Configuração do Vite
```

## 🎯 Conceitos React Demonstrados

1. **Estado (useState)**: Gerenciamento da lista de tarefas
2. **Eventos**: Click, Change, KeyPress
3. **Renderização Condicional**: Mensagem quando lista está vazia
4. **Mapeamento de Arrays**: Exibição da lista de tarefas
5. **Props e Componentes**: Estrutura básica de componentes

## 🏃‍♂️ Como Executar

1. **Instalar dependências**:
   ```bash
   npm install
   ```

2. **Iniciar servidor de desenvolvimento**:
   ```bash
   npm run dev
   ```

3. **Abrir no navegador**: Acesse `http://localhost:5173`

## 📱 Como Usar

1. Digite o nome da matéria no campo de texto
2. Pressione Enter ou clique em "Adicionar"
3. Clique sobre uma tarefa para marcá-la como concluída
4. Clique em "Excluir" para remover uma tarefa

## 🎨 Estilo

O projeto utiliza cores sólidas e design limpo:
- Azul (#3498db) para botões principais
- Vermelho (#e74c3c) para botões de exclusão
- Cinza claro para fundo
- Branco para o container principal

## 💡 Pontos para Explicar na Apresentação

1. **Gerenciamento de Estado**: Como o `useState` controla a lista
2. **Imutabilidade**: Por que criamos novos arrays em vez de modificar os existentes
3. **Event Handling**: Como React lida com interações do usuário
4. **Renderização**: Como o React atualiza a tela automaticamente

## 🔧 Possíveis Melhorias Futuras

- Persistência de dados (localStorage)
- Edição de tarefas
- Filtros (todas, concluídas, pendentes)
- Animações e transições
- Responsividade avançada
