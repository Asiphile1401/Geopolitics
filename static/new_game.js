(() => {
  'use strict';
  const filter = document.getElementById('country-search');
  const select = document.getElementById('country-select');
  const count = document.getElementById('country-count');
  if (!filter || !select) return;
  const choices = [...select.options].map(o => ({value: o.value, label: o.textContent}));
  filter.addEventListener('input', () => {
    const query = filter.value.trim().toLocaleLowerCase();
    const selected = select.value;
    const matches = choices.filter(c => c.label.toLocaleLowerCase().includes(query));
    const options = matches.map(c => {
      const option = new Option(c.label, c.value);
      option.selected = c.value === selected;
      return option;
    });
    select.replaceChildren(...options);
    select.disabled = options.length === 0;
    count.textContent = `${matches.length} of ${choices.length} countries found`;
    select.form.querySelector('button[type="submit"]').disabled = !options.length;
  });
})();
