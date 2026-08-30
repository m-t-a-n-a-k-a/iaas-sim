<script lang="ts">
  const navItems = ['Dashboard', 'Virtual Machines', 'Volumes', 'Operations', 'Usage'];
</script>

<svelte:head>
  <title>iaas-sim console</title>
</svelte:head>

<div class="shell">
  <aside class="sidebar">
    <h2>iaas-sim</h2>
    <nav>
      {#each navItems as item}
        <button type="button">{item}</button>
      {/each}
    </nav>
  </aside>

  <main class="main">
    <header class="header">
      <h1>Cloud Console</h1>
      <span>Phase 1 placeholder</span>
    </header>

    <section class="cards">
      <article class="card">
        <h3>System status</h3>
        <p>Operational health endpoints are available.</p>
      </article>
      <article class="card">
        <h3>API</h3>
        <p>FastAPI + OpenAPI are enabled.</p>
      </article>
      <article class="card">
        <h3>Observability</h3>
        <p>OTLP traces, metrics, and logs are configured.</p>
      </article>
    </section>
  </main>
</div>

<style>
  :global(body) {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #f8fafc;
    color: #0f172a;
  }

  .shell {
    display: flex;
    min-height: 100vh;
  }

  .sidebar {
    width: 220px;
    background: #0f172a;
    color: white;
    padding: 1.5rem 1rem;
    box-sizing: border-box;
  }

  .sidebar h2 {
    margin-top: 0;
  }

  nav {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  button {
    border: 0;
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    background: rgba(255, 255, 255, 0.08);
    color: white;
    text-align: left;
    font: inherit;
  }

  .main {
    flex: 1;
    padding: 2rem;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2rem;
  }

  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 1rem;
  }

  .card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 0.75rem;
    padding: 1.25rem;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }
</style>
