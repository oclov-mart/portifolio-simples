import React, { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [lista, setLista] = useState([])
  const [input, setInput] = useState('')
  const [carregado, setCarregado] = useState(false)

  // Carrega do localStorage apenas uma vez
  useEffect(() => {
    const dadosSalvos = localStorage.getItem('minhas_tarefas')
    console.log('Carregando do localStorage:', dadosSalvos)
    if (dadosSalvos) {
      try {
        const parseado = JSON.parse(dadosSalvos)
        console.log('Parseado:', parseado)
        setLista(parseado)
      } catch (e) {
        console.error('Erro ao parsear:', e)
      }
    }
    setCarregado(true)
  }, [])

  // Só salva depois de carregar e quando a lista mudar
  useEffect(() => {
    if (carregado) {
      console.log('Salvando no localStorage:', lista)
      localStorage.setItem('minhas_tarefas', JSON.stringify(lista))
    }
  }, [lista, carregado])

  function adicionar() {
    if (!input.trim()) return

    const nova = {
      id: Date.now(),
      texto: input,
      feita: false
    }

    setLista([...lista, nova])
    setInput('')
  }

  function marcarComoFeita(id) {
    setLista(
      lista.map(item => {
        if (item.id === id) {
          return { ...item, feita: !item.feita }
        }
        return item
      })
    )
  }

  function remover(id) {
    setLista(lista.filter(item => item.id !== id))
  }

  function tecla(e) {
    if (e.key === 'Enter') {
      adicionar()
    }
  }

  return (
    <div className="container">
      <h1>minha agenda de estudos</h1>

      <div className="input-area">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={tecla}
          placeholder="coloca aqui o que tu vai estudar"
        />

        <button onClick={adicionar}>
          adicionar
        </button>
      </div>

      <div>
        {lista.length === 0 && (
          <p>ainda não tem nada aqui</p>
        )}

        {lista.map(item => (
          <div key={item.id} className="item">
            <span
              onClick={() => marcarComoFeita(item.id)}
              style={{
                textDecoration: item.feita ? 'line-through' : 'none',
                cursor: 'pointer'
              }}
            >
              {item.texto}
            </span>

            <button onClick={() => remover(item.id)}>
              apagar
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

export default App
