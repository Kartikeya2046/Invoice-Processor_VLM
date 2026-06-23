import React from 'react';
import Dashboard from './pages/Dashboard';
import './index.css';

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Document Extraction System</h1>
      </header>
      <main>
        <Dashboard />
      </main>
    </div>
  );
}

export default App;
