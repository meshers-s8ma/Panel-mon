
module.exports = {
  plugins: {
    // Подключаем плагин Tailwind CSS.
    // Он будет сканировать ваши HTML и JS файлы (согласно tailwind.config.js)
    // и генерировать необходимые CSS-классы.
    tailwindcss: {},

    // Подключаем Autoprefixer.
    // Он автоматически добавит вендорные префиксы (-webkit-, -moz-, -ms-)
    // к CSS-правилам для обеспечения кроссбраузерной совместимости.
    autoprefixer: {},
  },
}