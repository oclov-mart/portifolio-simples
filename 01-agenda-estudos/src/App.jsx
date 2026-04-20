import React, { useState } from 'react'
import './App.css'

function App() {
  const [listaDeMaterias, setListaDeMaterias] = useState([])
  const [novaMateria, setNovaMateria] = useState('')

  const adicionarMateria = () => {
    const textoLimpo = novaMateria.trim()

    if (textoLimpo !== '') {
      const materia = {
        id: crypto.randomUUID(),
        texto: textoLimpo,
        completada: false
      }

      // tive que usar atualização funcional + spread para garantir que pego o estado mais novo sem mutar o original
      setListaDeMaterias((listaAtual) => [...listaAtual, materia])
      setNovaMateria('')
    }
  }

  const alternarCompletada = (id) => {
    setListaDeMaterias((listaAtual) =>
      listaAtual.map((materia) =>
        materia.id === id
          ? { ...materia, completada: !materia.completada }
          : materia
      )
    )
  }

  const excluirMateria = (id) => {
    setListaDeMaterias((listaAtual) =>
      listaAtual.filter((materia) => materia.id !== id)
    )
  }

  const handleTecla = (evento) => {
    if (evento.key === 'Enter') {
      adicionarMateria()
    }
  }

  return (
    <div className="container">
      <h1>Agenda de Estudos do Clóvis</h1>

      <div className="input-container">
        <input
          type="text"
          value={novaMateria}
          onChange={(evento) => setNovaMateria(evento.target.value)}
          onKeyDown={handleTecla}
          placeholder="Digite a matéria para estudar..."
          className="input-tarefa"
        />
        <button onClick={adicionarMateria} className="botao-adicionar">
          Adicionar
        </button>
      </div>

      <div className="lista-container">
        {listaDeMaterias.length === 0 ? (
          <p className="mensagem-vazia">Nenhuma tarefa adicionada ainda.</p>
        ) : (
          listaDeMaterias.map((materia) => (
            <div key={materia.id} className="tarefa-item">
              <span
                onClick={() => alternarCompletada(materia.id)}
                className={`tarefa-texto ${materia.completada ? 'completada' : ''}`}
              >
                {materia.texto}
              </span>
              <button
                onClick={() => excluirMateria(materia.id)}
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
