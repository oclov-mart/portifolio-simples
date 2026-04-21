import React, { useState } from 'react'
import './App.css'

function App() {
  const [listaDeMaterias, setListaDeMaterias] = useState([])
  const [novaMateria, setNovaMateria] = useState('')

  const adicionarMateria = () => {
    const materiaDigitada = novaMateria.trim()

    if (materiaDigitada === '') return

    const jaExiste = listaDeMaterias.some(
      (materia) => materia.texto.toLowerCase() === materiaDigitada.toLowerCase()
    )

    if (jaExiste) {
      alert('Essa matéria já está na lista.')
      return
    }

    const materiaNova = {
      id: Date.now() + Math.random(),
      texto: materiaDigitada,
      completada: false
    }

    // aqui usei spread pra montar uma lista nova e não mexer direto na lista antiga
    setListaDeMaterias([...listaDeMaterias, materiaNova])
    setNovaMateria('')
  }

  const alternarCompletada = (id) => {
    const novaLista = listaDeMaterias.map((materia) => {
      if (materia.id === id) {
        return { ...materia, completada: !materia.completada }
      }
      return materia
    })

    setListaDeMaterias(novaLista)
  }

  const excluirMateria = (id) => {
    const novaLista = listaDeMaterias.filter((materia) => materia.id !== id)
    setListaDeMaterias(novaLista)
  }

  const apertouTecla = (evento) => {
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
          onKeyDown={apertouTecla}
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
