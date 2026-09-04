export type SellerStatus = "correct" | "unconfirmed" | "incorrect";

export interface Seller {
  seller_id: string;
  name: string;
  link_to_seller: string;
  link_to_card: string;
  status: SellerStatus;
  email: string;
  ogrn: string;
  official_name: string;
  inn: string;
  phone: string;
  rating: number | null;
}

export interface SellerUpdate {
  seller_id: string;
  link_to_seller?: string;
  link_to_card?: string;
  status?: SellerStatus;
  email?: string;
  ogrn?: string;
  official_name?: string;
  inn?: string;
  phone?: string;
  rating?: number | null;
}

export interface DefineSellersResult {
  added: number;
  selected: number;
  processed: number;
  confirmed: number;
  incorrect: number;
  unknown: number;
  stopped_reason: string;
}

export type ViewName = "sellers" | "operations";
