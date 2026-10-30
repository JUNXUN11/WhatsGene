<template>
  <div>
    <header class="site-header">
      <NuxtLink to="/" class="brand">Whats<span>Gene</span></NuxtLink>
      <nav>
        <NuxtLink to="/">How it works</NuxtLink>
        <NuxtLink to="/jobs">Workflows</NuxtLink>
      </nav>
    </header>
    <NuxtPage />
    <footer class="site-footer">
      For research and education only. Every results page shows the backend, program, database and exact parameters; only remote (NCBI) jobs send sequences to NCBI.
      Built with Muse Spark Open.
    </footer>
  </div>
</template>
