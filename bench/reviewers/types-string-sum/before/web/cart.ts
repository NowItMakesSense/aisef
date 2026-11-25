export interface CartItem {
  sku: string;
  price: number;
  qty: number;
}

export function cartTotal(items: CartItem[]): number {
  return items.reduce((sum, i) => sum + i.price * i.qty, 0);
}
