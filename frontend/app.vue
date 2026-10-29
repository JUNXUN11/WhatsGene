<template>
  <div>
    <header class="site-header">
      <NuxtLink to="/" class="brand">Whats<span>Gene</span></NuxtLink>
      <nav>
        <NuxtLink to="/">How it works</NuxtLink>
        <NuxtLink to="/jobs">Recent jobs</NuxtLink>
      </nav>
    </header>
    <NuxtPage />
    <footer class="site-footer">
      For research and education only. Sequences are sent to NCBI's public BLAST service.
      Built with Muse Spark Open.
    </footer>
  </div>
</template>
