// API types mirroring backend/app/schemas (source of truth: pydantic models).

export type UUID = string;
export type ISODate = string;

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface TokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type Role = "owner" | "admin" | "manager" | "mechanic" | "viewer";

export interface User {
  id: UUID;
  email: string;
  name: string;
  role: Role;
  is_active: boolean;
  created_at: ISODate;
  last_login_at: ISODate | null;
}

export interface Plan {
  id: string;
  name: string;
  price_monthly_usd: number;
  features: Record<string, boolean>;
  limits: Record<string, number>;
}

export interface TenantInfo {
  id: UUID;
  slug: string;
  name: string;
  plan: string;
  status: string;
  region: string;
}

export interface Me {
  user: User;
  tenant: TenantInfo;
  entitlements: Plan;
}

export interface Branding {
  slug: string;
  display_name: string;
  primary_color: string;
  accent_color: string;
  logo_url: string | null;
  support_email: string | null;
  currency: string;
  locale: string;
}

export interface SlugCheck {
  slug: string;
  available: boolean;
  message: string | null;
}

export interface SignupResponse {
  tenant_id: string;
  slug: string;
  url: string;
  access_token: string;
  token_type: string;
  expires_in: number;
}

// --- fleet ---------------------------------------------------------------

export type VehicleStatus = "active" | "in_service" | "retired";
export type FuelType = "petrol" | "diesel" | "electric" | "hybrid" | "lpg" | "other";

export interface VehicleSummary {
  id: UUID;
  plate_number: string;
  make: string;
  model: string;
  year: number | null;
  status: VehicleStatus;
  customer_name: string | null;
  open_orders: number;
}

export interface Vehicle {
  id: UUID;
  plate_number: string;
  make: string;
  model: string;
  year: number | null;
  vin: string | null;
  color: string | null;
  fuel_type: FuelType;
  mileage: number;
  status: VehicleStatus;
  customer_id: UUID | null;
  notes: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface VehicleIn {
  plate_number: string;
  make: string;
  model: string;
  year?: number | null;
  vin?: string | null;
  color?: string | null;
  fuel_type?: FuelType;
  mileage?: number;
  customer_id?: UUID | null;
  notes?: string | null;
}

// --- customers -----------------------------------------------------------

export interface CustomerSummary {
  id: UUID;
  name: string;
  phone: string | null;
  vehicle_count: number;
  open_orders: number;
  total_billed: string;
}

export interface Customer {
  id: UUID;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  notes: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface CustomerIn {
  name: string;
  email?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
}

// --- service orders ------------------------------------------------------

export type OrderStatus =
  | "scheduled"
  | "in_progress"
  | "awaiting_parts"
  | "completed"
  | "invoiced"
  | "cancelled";
export type OrderPriority = "low" | "normal" | "high" | "urgent";
export type ItemKind = "labor" | "part";

export interface OrderItem {
  id: UUID;
  kind: ItemKind;
  part_id: UUID | null;
  description: string;
  quantity: string;
  unit_price: string;
  total: string;
}

export interface Order {
  id: UUID;
  number: string;
  status: OrderStatus;
  priority: OrderPriority;
  description: string;
  vehicle_id: UUID;
  customer_id: UUID | null;
  mechanic_id: UUID | null;
  location_id: UUID | null;
  odometer: number | null;
  scheduled_at: ISODate | null;
  started_at: ISODate | null;
  completed_at: ISODate | null;
  estimated_cost: string | null;
  notes: string | null;
  created_at: ISODate;
  updated_at: ISODate;
  items: OrderItem[];
  totals: { labor?: string; parts?: string; total?: string };
}

export interface OrderListItem {
  id: UUID;
  number: string;
  status: OrderStatus;
  priority: OrderPriority;
  description: string;
  vehicle_plate: string | null;
  customer_name: string | null;
  mechanic_name: string | null;
  location_name: string | null;
  total: string;
  created_at: ISODate;
}

export interface OrderIn {
  vehicle_id: UUID;
  location_id?: UUID | null;
  description: string;
  priority?: OrderPriority;
  odometer?: number | null;
  scheduled_at?: ISODate | null;
  mechanic_id?: UUID | null;
  estimated_cost?: number | null;
  notes?: string | null;
}

export interface ItemIn {
  kind: ItemKind;
  description: string;
  quantity: number;
  unit_price: number;
}

// --- invoices ------------------------------------------------------------

export type InvoiceStatus = "draft" | "sent" | "paid" | "overdue" | "void";

export interface Invoice {
  id: UUID;
  number: string;
  order_id: UUID | null;
  customer_id: UUID | null;
  status: InvoiceStatus;
  issued_at: ISODate | null;
  due_at: ISODate | null;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  total: string;
  currency: string;
  paid_at: ISODate | null;
  payment_url: string | null;
  payment_provider: string | null;
  lines: Array<{
    description?: string;
    kind?: string;
    quantity?: string | number;
    unit_price?: string | number;
    total?: string | number;
  }>;
  meta: Record<string, unknown>;
  created_at: ISODate;
}

export interface InvoiceListItem {
  id: UUID;
  number: string;
  status: InvoiceStatus;
  customer_name: string | null;
  total: string;
  currency: string;
  issued_at: ISODate | null;
  due_at: ISODate | null;
}

// --- dashboard / audit / staff / keys / domains --------------------------

export interface DashboardStats {
  vehicles_total: number;
  vehicles_in_service: number;
  customers_total: number;
  orders_open: number;
  orders_by_status: Record<string, number>;
  revenue_mtd: string;
  revenue_30d: string;
  unpaid_total: string;
  unpaid_count: number;
  upcoming: Array<{
    id: UUID;
    number: string;
    status: OrderStatus;
    priority: OrderPriority;
    scheduled_at: string | null;
    vehicle_plate: string | null;
    customer_name: string | null;
  }>;
  recent_orders: Array<{
    id: UUID;
    number: string;
    status: OrderStatus;
    priority?: OrderPriority;
    vehicle_plate?: string | null;
    customer_name?: string | null;
    total?: string;
    created_at?: ISODate;
  }>;
}

export interface AuditEntry {
  id: UUID;
  user_id: UUID | null;
  user_name: string | null;
  action: string;
  entity: string;
  entity_id: string | null;
  meta: Record<string, unknown>;
  ip: string | null;
  created_at: ISODate;
}

export interface ApiKey {
  id: UUID;
  name: string;
  last_used_at: ISODate | null;
  created_at: ISODate;
  revoked_at: ISODate | null;
}

export interface ApiKeyCreated {
  id: UUID;
  name: string;
  key: string;
  warning: string;
}

export interface Domain {
  domain: string;
  status: string;
  verification_token: string;
  txt_record: string;
  created_at: string | null;
  verified_at: string | null;
}

export interface BillingStatus {
  plan: string;
  status: string;
  provider: string;
  currency: string;
  current_period_end: string | null;
  checkout_available: boolean;
  portal_available: boolean;
}

export interface CheckoutResponse {
  url: string | null;
  message: string;
}

export interface Ok {
  ok: boolean;
  detail?: string | null;
}

// --- estimates / share links / VIN ----------------------------------------

export type EstimateStatus = "draft" | "sent" | "approved" | "declined";

export interface Estimate {
  id: UUID;
  number: string;
  status: EstimateStatus;
  description: string;
  vehicle_id: UUID;
  customer_id: UUID | null;
  notes: string | null;
  sent_at: ISODate | null;
  responded_at: ISODate | null;
  responded_by_name: string | null;
  converted_order_id: UUID | null;
  created_at: ISODate;
  updated_at: ISODate;
  items: OrderItem[];
  totals: { labor?: string; parts?: string; total?: string };
}

export interface EstimateListItem {
  id: UUID;
  number: string;
  status: EstimateStatus;
  description: string;
  vehicle_plate: string | null;
  customer_name: string | null;
  total: string;
  created_at: ISODate;
}

export interface ShareLink {
  token: string;
  url_path: string;
  kind: string;
}

export interface PublicWorkspace {
  display_name: string;
  primary_color: string;
  accent_color: string;
  currency: string;
  support_email: string | null;
}

export interface PublicVehicle {
  plate_number: string | null;
  make: string | null;
  model: string | null;
  year: number | null;
}

export interface PublicOrder {
  workspace: PublicWorkspace;
  number: string;
  status: OrderStatus;
  description: string;
  vehicle: PublicVehicle;
  scheduled_at: ISODate | null;
  completed_at: ISODate | null;
  updated_at: ISODate;
  items: Array<{ kind: ItemKind; description: string }>;
  inspection: Array<{
    label: string;
    status: InspectionItemStatus;
    note: string | null;
    photos: string[];
  }>;
  inspection_completed: boolean;
}

export interface PublicEstimate {
  workspace: PublicWorkspace;
  number: string;
  status: EstimateStatus;
  description: string;
  vehicle: PublicVehicle;
  items: Array<{
    kind: ItemKind;
    description: string;
    quantity: string;
    unit_price: string;
    total: string;
  }>;
  totals: { labor: string; parts: string; total: string };
  sent_at: ISODate | null;
  responded_at: ISODate | null;
  responded_by_name: string | null;
  converted_order_number: string | null;
}

export interface VinDecode {
  vin: string;
  decoded: boolean;
  make: string | null;
  model: string | null;
  year: number | null;
  trim: string | null;
  body_class: string | null;
  fuel_type: FuelType | null;
  engine: string | null;
  vehicle_type: string | null;
  message: string | null;
}

// --- Tier B: DVI, notifications, booking, reviews -------------------------

export type InspectionStatus = "draft" | "completed";
export type InspectionItemStatus = "ok" | "attention" | "critical" | "na";

export interface InspectionPhoto {
  path: string;
  mime: string;
  size: number;
  name: string;
}

export interface InspectionItem {
  id: UUID;
  label: string;
  status: InspectionItemStatus;
  note: string | null;
  photos: InspectionPhoto[];
  sort_order: number;
  created_at: ISODate;
}

export interface Inspection {
  id: UUID;
  order_id: UUID;
  status: InspectionStatus;
  notes: string | null;
  completed_at: ISODate | null;
  created_at: ISODate;
  updated_at: ISODate;
  items: InspectionItem[];
}

export interface NotificationRow {
  id: UUID;
  channel: string;
  recipient: string;
  template: string;
  body: string;
  status: "queued" | "sent" | "failed" | "skipped";
  provider: string | null;
  error: string | null;
  entity_type: string | null;
  entity_id: UUID | null;
  sent_at: ISODate | null;
  created_at: ISODate;
}

export interface ReviewRequest {
  id: UUID;
  order_id: UUID;
  status: "pending" | "submitted";
  rating: number | null;
  comment: string | null;
  submitted_at: ISODate | null;
  created_at: ISODate;
  url_path: string | null;
  order_number: string | null;
}

export interface PublicReview {
  workspace: PublicWorkspace;
  order_number: string;
  status: "pending" | "submitted";
  rating: number | null;
  comment: string | null;
  submitted_at: ISODate | null;
  review_url: string | null;
}

export interface BookingSlot {
  start: ISODate;
  label: string;
  available: boolean;
}

export interface PublicBooking {
  workspace: PublicWorkspace;
  booking_enabled: boolean;
  timezone: string;
  slots: BookingSlot[];
  review_url: string | null;
}

export interface BookingResult {
  number: string;
  scheduled_at: ISODate;
  message: string;
}

export interface OperationsSettings {
  booking_enabled: boolean;
  business_hours: Record<string, string[][]>;
  review_url: string | null;
  timezone: string;
}

// --- inventory -----------------------------------------------------------

export interface Part {
  id: UUID;
  sku: string;
  name: string;
  category: string | null;
  brand: string | null;
  supplier: string | null;
  location: string | null;
  cost: string;
  price: string;
  stock_qty: string;
  reorder_level: string;
  active: boolean;
  notes: string | null;
  created_at: ISODate;
  updated_at: ISODate;
}

export interface StockMovement {
  id: UUID;
  part_id: UUID;
  delta: string;
  reason: "received" | "issued" | "returned" | "adjustment";
  note: string | null;
  order_id: UUID | null;
  user_id: UUID | null;
  created_at: ISODate;
}

export interface InventorySummary {
  parts: number;
  low_stock: number;
  stock_value: string;
}

// --- suppliers -----------------------------------------------------------

export interface SupplierConnection {
  id: UUID;
  name: string;
  provider: "stub" | "csv";
  portal_url: string | null;
  catalog_size: number;
  created_at: ISODate;
}

export interface SupplierOffer {
  connection_id: UUID;
  supplier: string;
  sku: string;
  brand: string | null;
  description: string;
  cost: string;
  price: string;
  stock_qty: string;
  portal_url: string | null;
}

export interface CatalogImportResult {
  imported: number;
  updated: number;
  skipped: number;
}

// --- accounting ----------------------------------------------------------

export interface AccountingConnection {
  provider: "stub" | "quickbooks" | "xero";
  status: "connected" | "disconnected" | "error";
  external_tenant_id: string | null;
  accounts: Record<string, string>;
  last_synced_at: ISODate | null;
}

export interface AccountingRun {
  id: UUID;
  provider: string;
  period_start: string;
  period_end: string;
  status: "pending" | "succeeded" | "failed" | "partial";
  invoices_count: number;
  total_amount: string;
  currency: string;
  detail: string | null;
  created_at: ISODate;
  completed_at: ISODate | null;
}

export interface AccountingStatus {
  provider: "stub" | "quickbooks" | "xero";
  configured: boolean;
  connection: AccountingConnection | null;
  pending_invoices: number;
  last_run: AccountingRun | null;
}

export interface AccountingConnectResult {
  connected: boolean;
  authorize_url: string | null;
  message: string;
}

// --- marketing -----------------------------------------------------------

export type CampaignChannel = "sms" | "email";
export type CampaignSegment = "all" | "inactive" | "due_service";
export type CampaignStatus = "draft" | "sent";

export interface Campaign {
  id: UUID;
  name: string;
  channel: CampaignChannel;
  segment: CampaignSegment;
  lookback_days: number;
  body: string;
  status: CampaignStatus;
  recipients_count: number;
  sent_count: number;
  skipped_count: number;
  failed_count: number;
  sent_at: ISODate | null;
  created_at: ISODate;
}

export interface CampaignRecipient {
  id: UUID;
  customer_id: UUID | null;
  recipient: string;
  status: "pending" | "sent" | "failed" | "skipped";
  error: string | null;
  created_at: ISODate;
}

export interface CampaignDetail extends Campaign {
  recipients: CampaignRecipient[];
}

export interface CampaignPreview {
  customers_count: number;
  recipients_count: number;
}

// --- locations -----------------------------------------------------------

export interface Location {
  id: UUID;
  name: string;
  address: string | null;
  phone: string | null;
  is_default: boolean;
  created_at: ISODate;
  updated_at: ISODate;
}
