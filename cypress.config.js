
const { defineConfig } = require('cypress');

module.exports = defineConfig({
  e2e: {
    baseUrl: 'http://web:5000',
    supportFile: false,

    // --- НАЧАЛО ИЗМЕНЕНИЯ ---
    // Устанавливаем размер окна браузера по умолчанию для всех тестов.
    // 1280x720 - это стандартный размер для десктопных тестов,
    // который гарантирует, что адаптивные стили (sm:block) сработают.
    viewportWidth: 1280,
    viewportHeight: 720,
    // --- КОНЕЦ ИЗМЕНЕНИЯ ---

    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
  },
});