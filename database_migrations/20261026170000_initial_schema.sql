create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
    new.updated_at = timezone('utc', now());
    return new;
end;
$$;

create table public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, display_name)
    values (
        new.id,
        nullif(trim(new.raw_user_meta_data ->> 'display_name'), '')
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute procedure public.handle_new_user();

create trigger profiles_set_updated_at
    before update on public.profiles
    for each row execute procedure public.set_updated_at();

create table public.products (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    product_id text not null,
    product_name text not null,
    category text,
    size text,
    unit_price numeric(14, 2),
    cost_price numeric(14, 2),
    brand text,
    description text,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint products_user_product_id_key unique (user_id, product_id),
    constraint products_unit_price_nonnegative
        check (unit_price is null or unit_price >= 0),
    constraint products_cost_price_nonnegative
        check (cost_price is null or cost_price >= 0)
);

create trigger products_set_updated_at
    before update on public.products
    for each row execute procedure public.set_updated_at();

create table public.transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    transaction_id text not null,
    transaction_date date not null,
    customer_id text not null,
    product_id text not null,
    product_name text not null,
    category text not null,
    quantity numeric(14, 4) not null,
    unit_price numeric(14, 2) not null,
    cost_price numeric(14, 2) not null,
    region text not null,
    discount numeric(14, 2) not null default 0,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint transactions_user_transaction_id_key
        unique (user_id, transaction_id),
    constraint transactions_quantity_positive check (quantity > 0),
    constraint transactions_unit_price_nonnegative check (unit_price >= 0),
    constraint transactions_cost_price_nonnegative check (cost_price >= 0),
    constraint transactions_discount_nonnegative check (discount >= 0)
);

create index transactions_user_date_idx
    on public.transactions (user_id, transaction_date);

create index transactions_user_customer_idx
    on public.transactions (user_id, customer_id);

create index transactions_user_product_idx
    on public.transactions (user_id, product_id);

create trigger transactions_set_updated_at
    before update on public.transactions
    for each row execute procedure public.set_updated_at();

create table public.inventory (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users (id) on delete cascade,
    product_id text not null,
    inventory_date date not null,
    stock_quantity numeric(14, 4) not null,
    reorder_level numeric(14, 4) not null,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    constraint inventory_user_product_date_key
        unique (user_id, product_id, inventory_date),
    constraint inventory_stock_quantity_nonnegative check (stock_quantity >= 0),
    constraint inventory_reorder_level_nonnegative check (reorder_level >= 0)
);

create index inventory_user_product_date_idx
    on public.inventory (user_id, product_id, inventory_date desc);

create trigger inventory_set_updated_at
    before update on public.inventory
    for each row execute procedure public.set_updated_at();

alter table public.profiles enable row level security;
alter table public.products enable row level security;
alter table public.transactions enable row level security;
alter table public.inventory enable row level security;

create policy "Users can view their own profile"
    on public.profiles for select
    using ((select auth.uid()) = id);

create policy "Users can update their own profile"
    on public.profiles for update
    using ((select auth.uid()) = id)
    with check ((select auth.uid()) = id);

create policy "Users can view their own products"
    on public.products for select
    using ((select auth.uid()) = user_id);

create policy "Users can insert their own products"
    on public.products for insert
    with check ((select auth.uid()) = user_id);

create policy "Users can update their own products"
    on public.products for update
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own products"
    on public.products for delete
    using ((select auth.uid()) = user_id);

create policy "Users can view their own transactions"
    on public.transactions for select
    using ((select auth.uid()) = user_id);

create policy "Users can insert their own transactions"
    on public.transactions for insert
    with check ((select auth.uid()) = user_id);

create policy "Users can update their own transactions"
    on public.transactions for update
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own transactions"
    on public.transactions for delete
    using ((select auth.uid()) = user_id);

create policy "Users can view their own inventory"
    on public.inventory for select
    using ((select auth.uid()) = user_id);

create policy "Users can insert their own inventory"
    on public.inventory for insert
    with check ((select auth.uid()) = user_id);

create policy "Users can update their own inventory"
    on public.inventory for update
    using ((select auth.uid()) = user_id)
    with check ((select auth.uid()) = user_id);

create policy "Users can delete their own inventory"
    on public.inventory for delete
    using ((select auth.uid()) = user_id);
