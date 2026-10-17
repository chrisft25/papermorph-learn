/* Spanish (Mexico) interface text for this book. The shared engine ships only en and ru, and its copy in lib/ is not
   edited by hand, so the Spanish table lives here until it is added at the engine's source.
   - Lessons: load after engine.js; it adds TRANSLATIONS.es, which the engine reads when <html lang="es">.
   - Cover/contents: load after contents.js; call EsBook.contents() right after Contents.book(...). contents.js keeps
     its table private, so this rewrites the few strings it generated. */
'use strict';
(() => {
  const ES = {
    decimalSign: '.', stageLabel: 'Animación de la lección', stageLabelTitled: 'Animación de la lección: {title}',
    shortcuts: 'Atajos de teclado', lesson: 'Lección', questions: 'Preguntas',
    helpPlay: 'Reproducir o pausar', helpStep: 'Paso anterior o siguiente', helpStepInQuestion: 'Cambiar de paso durante una pregunta', helpRestart: 'Empezar de nuevo',
    helpCaptions: 'Subtítulos sí o no', helpSpeed: 'Más lento o más rápido', helpFullScreen: 'Pantalla completa', helpList: 'Mostrar esta lista',
    helpChoose: 'Elegir una respuesta', helpTrueFalse: 'Verdadero o falso', helpRows: 'Moverse entre filas',
    helpNumberLine: 'Moverse por la recta numérica', helpEnter: 'Revisar y luego continuar',
    helpShowAnswer: 'Mostrar la respuesta', helpLeaveBox: 'Salir de una casilla', helpClose: 'Presiona {key} para cerrar.',
    paused: 'En pausa. Presiona espacio o haz clic para continuar.',
    soundFailed: 'No se pudo reproducir el sonido. La lección sigue con el texto en pantalla.',
    startLesson: 'Empezar la lección', coverKeys: 'Presiona {space} para empezar, {help} para ver los atajos.', spaceKey: 'Espacio',
    chapterNumber: 'Capítulo {n}', aboutMinutes: 'Unos {n} minutos, con audio y preguntas rápidas.',
    allChapters: 'Todos los capítulos', playLabel: 'Reproducir o pausar (espacio)', backLabel: 'Paso anterior (flecha izquierda)', restartLabel: 'Reiniciar la lección',
    volumeLabel: 'Ajustar el volumen', volumeTitle: 'Volumen (0 = silencio)', volumeSlider: 'Volumen',
    helpLabel: 'Atajos de teclado (?)', speedLabel: 'Velocidad (< y >)', captionsLabel: 'Subtítulos (C)', fullScreenLabel: 'Pantalla completa', goToStep: 'Ir al paso {n}: {title}',
    quickCheck: 'Pregunta rápida', countOf: '{k} de {n}', check: 'Revisar', showAnswer: 'Mostrar la respuesta', nextQuestion: 'Siguiente pregunta', continue: 'Continuar',
    correct: 'Correcto. ', notQuite: 'Todavía no. ', answerPrefix: 'Respuesta: ', keysPrefix: 'Teclas: ',
    hintMove: ' moverse, ', hintChoose: ' elegir', hintChooseOrClickGrid: ' elegir, o haz clic en la tabla', hintMoveAlongLine: ' moverse por la recta, ',
    hintChooseOrClick: ' elegir, o haz clic', hintRow: ' fila, ', hintTypeFraction: 'escribe números como 3/4 o −2 1/4, ', hintTypeNumber: 'escribe el número, ',
    hintTypeDecimal: 'escribe el número, ', hintNextBox: ' siguiente casilla, ', hintCheck: ' revisar, ', hintLeaveBox: ' salir de la casilla',
    hintPickNumber: ' elegir un número, ', hintPickRing: ' elegir su anillo',
    rowsRight: '{r} de {n} correctas. Corrige las filas marcadas con ✗ y revisa de nuevo.',
    choicesShown: 'ya están marcadas las opciones correctas.', numbersShown: 'ya están escritos los números correctos.',
    notPlacedYet: '{x} todavía no está colocado.',
    ringsRight: '{r} de {n} en el anillo correcto.', ringsShown: 'cada número está ahora en su anillo más pequeño.',
    chipPlaced: '{x}, colocado en {ring}', chipNotPlaced: '{x}, sin colocar', pointLabel: 'El punto {v}', answerBox: 'Respuesta',
    trueLabel: 'Verdadero', falseLabel: 'Falso',
    chapterComplete: 'Capítulo {n} terminado', quickChecks: 'Preguntas rápidas', chapterPractice: 'Práctica del capítulo',
    firstTryScore: '{name}: {r} de {t} correctas al primer intento.', notAttempted: '{name}: sin intentar.',
    watchAgain: 'Ver de nuevo', nextChapter: 'Siguiente capítulo',
  };
  if (typeof TRANSLATIONS === 'object') {   // the engine's table (lessons)
    TRANSLATIONS.es = ES;
    // Interface the engine built while it loaded (before this table existed): swap exact English strings for Spanish.
    const en = TRANSLATIONS.en, swap = {};
    for (const k in ES) if (typeof en[k] === 'string' && !/\{/.test(en[k])) swap[en[k]] = ES[k];
    const fix = () => {
      if (!/^es/.test(document.documentElement.lang)) return;
      document.querySelectorAll('[aria-label], [title]').forEach(e => ['aria-label', 'title'].forEach(a => {
        const v = e.getAttribute(a); if (v && swap[v]) e.setAttribute(a, swap[v]);
      }));
      const w = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) { const v = n.nodeValue.trim(); if (v && swap[v]) n.nodeValue = n.nodeValue.replace(v, swap[v]); }
      // the start card's key line (built with placeholders): keep its #coverMeta span, rewrite the rest
      const cm = document.getElementById('coverMeta'), small = cm?.parentElement;
      if (small && !small.dataset.es) {
        small.dataset.es = '1';
        [...small.childNodes].forEach(n => { if (n !== cm) n.remove(); });
        small.insertAdjacentHTML('beforeend', ' ' + ES.coverKeys.replace('{space}', `<kbd>${ES.spaceKey}</kbd>`).replace('{help}', '<kbd>?</kbd>'));
      }
    };
    fix(); addEventListener('DOMContentLoaded', fix); addEventListener('load', fix);
  }

  // Cover and contents.
  const plural = (n, one, other) => (n === 1 ? one : other).replace('{n}', n);
  const C = {
    open: 'Abrir el libro', toCover: 'Volver a la portada', doneMark: '✓ Terminado · ', lastMark: ' · Abierto por última vez',
  };
  function contents() {
    if (!/^es/.test(document.documentElement.lang)) return;
    document.querySelectorAll('[data-t]').forEach(e => { if (C[e.dataset.t]) e.firstChild.nodeValue = C[e.dataset.t]; });
    document.querySelectorAll('[data-t-label]').forEach(e => { if (C[e.dataset.tLabel]) e.setAttribute('aria-label', C[e.dataset.tLabel]); });
    const root = document.documentElement.style;
    root.setProperty('--done', JSON.stringify(C.doneMark)); root.setProperty('--last', JSON.stringify(C.lastMark));
    document.querySelectorAll('.unit h2 .label').forEach(e => { e.textContent = e.textContent.replace(/^Unit (\d+)/, 'Parte $1'); });
    const cards = document.querySelectorAll('#units a.ch'), total = cards.length;
    const done = document.querySelectorAll('#units a.ch.done').length;
    const prog = document.getElementById('prog');
    if (prog) prog.innerHTML = done ? `<b>${done}</b> de ${total} terminados` : plural(total, '{n} capítulo', '{n} capítulos');
    const meta = document.getElementById('meta'), units = document.querySelectorAll('#units .unit').length;
    if (meta) meta.textContent = `${plural(total, '{n} capítulo listo', '{n} capítulos listos')} · ${plural(units, '{n} parte', '{n} partes')} · con audio`;
    const r = document.getElementById('resume');
    if (r && !r.hidden) r.textContent = r.textContent.replace(/^Continue · Chapter (\d+)/, 'Continuar · Capítulo $1');
  }
  window.EsBook = { contents };
})();
