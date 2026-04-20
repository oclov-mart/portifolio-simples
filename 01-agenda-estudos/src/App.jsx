import React, { useState } from 'react'
import './App.css'

function App() {
  const [lista, setLista] = useState([])
  const [novaTarefa, setNovaTarefa] = useState('')

  const adicionarTarefa = () => {
    if (novaTarefa.trim() !== '') {
      const tarefa = {
        id: Date.now(),
        texto: novaTarefa,
        completada: false
      }
      setLista([...lista, tarefa])
      setNovaTarefa('')
    }
  }

  const alternarCompletada = (id) => {
    setLista(lista.map(tarefa => 
      tarefa.id === id 
        ? { ...tarefa, completada: !tarefa.completada }
        : tarefa
    ))
  }

  const excluirTarefa = (id) => {
    setLista(lista.filter(tarefa => tarefa.id !== id))
  }

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      adicionarTarefa()
    }
  }

  return (
    <div className="container">
      {/* Mudei o título aqui para personalizar meu primeiro projeto */}
      <h1>Agenda de Estudos do Clóvis</h1>
      
      <div className="input-container">
        <input
          type="text"
          value={novaTarefa}
          onChange={(e) => setNovaTarefa(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Digite a matéria para estudar..."
          className="input-tarefa"
        />
        <button onClick={adicionarTarefa} className="botao-adicionar">
          Adicionar
        </button>
      </div>

      <div className="lista-container">
        {lista.length === 0 ? (
          <p className="mensagem-vazia">Nenhuma tarefa adicionada ainda.</p>
        ) : (
          lista.map(tarefa => (
            <div key={tarefa.id} className="tarefa-item">
              <span
                onClick={() => alternarCompletada(tarefa.id)}
                className={`tarefa-texto ${tarefa.completada ? 'completada' : ''}`}
              >
                {tarefa.texto}
              </span>
              <button
                onClick={() => excluirTarefa(tarefa.id)}
                className="botao-excluir"
              >
                Excluir
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

export default App
