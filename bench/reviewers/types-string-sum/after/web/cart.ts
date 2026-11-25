export interface CartItem {
  sku: string;
  price: string; // vem do formulario como texto, ex.: "19.90"
  qty: number;
}

export function cartTotal(items: CartItem[]): number {
  return items.reduce((sum: any, i) => sum + i.price, 0) as number;
}
