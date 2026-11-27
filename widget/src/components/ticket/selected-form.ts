let selectedForm: number | null = null;

export const clearSelectedForm = (): void => {
  selectedForm = null;
};

export const setSelectedForm = (id: number): void => {
  selectedForm = id;
};

export const getSelectedForm = (): number | null => selectedForm;