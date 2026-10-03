# Scenario B: Master Pricer - Unified Translation Specification

This master specification defines the architectural rules, type mappings, and safety invariants for translating the Master Pricer C++ codebase to Rust.

## Table of Contents
1. [Type Mappings](#1-type-mappings)
2. [Ownership & Lifetime Patterns](#2-ownership--lifetime-patterns)
3. [Error Handling (Exceptions -> Results)](#3-error-handling-exceptions---results)
4. [Concurrency & Thread Safety](#4-concurrency--thread-safety)
5. [System Invariants](#5-system-invariants)
6. [Module Function Contracts](#6-module-function-contracts)

## 1. Type Mappings
| C++ Type | Rust Type | Ownership | Notes |
|----------|-----------|-----------|-------|
| `CacheKey` | `struct CacheKey { /* fields */ }` | `owned` | Represents a unique cache key derived from SearchRequest parameters. |
| `CacheManager` | `struct CacheManager` | `Arc<CacheManager>` | Singleton cache implementation |
| `CacheStatistics` | `struct CacheStatistics { /* fields */ }` | `owned` | Tracks cache hits, misses, puts, and invalidations. |
| `CacheTransactionContext` | `struct CacheTransactionContext { /* fields */ }` | `owned` | Context for cache transactions (not fully implemented). |
| `Fare` | `struct Fare { carrier: String, origin: String, destination: String, base_price: f64, fare_class: String }` | `owned` | Direct translation of value type with owned String fields |
| `Flight` | `struct Flight { carrier: String, flight_no: String, origin: String, destination: String, dep_time: String, arr_time: String }` | `owned` | Direct translation of value type with owned String fields |
| `Itinerary` | `struct Itinerary` | `owned` | Represents a flight itinerary with legs and pricing details |
| `LogicalEntity` | `struct LogicalEntity` | `owned` | Contains collection of flights for a search |
| `SearchRequest` | `struct SearchRequest { origin: String, destination: String, date: String, num_passengers: i32 }` | `owned` | Direct translation of value type with owned String fields |
| `SearchResults` | `SearchResults` | `owned` | Value type. Contains status, message, time, cache flag. No complex ownership semantics. |
| `SearchStatus` | `enum SearchStatus` | `owned` | Enumeration of possible search outcomes |
| `Timer` | `struct Timer` | `owned` | Measures elapsed time |
| `bool` | `bool` | `owned` | Primitive type remains same |
| `const Fare*` | `&Fare` | `&` | Pointer to Fare becomes reference in Rust |
| `const SearchRequest&` | `&SearchRequest` | `&` | Immutable reference. Ensure SearchRequest implements Clone if needed for internal caching, but pass by ref for API. |
| `const std::vector<std::string>&` | `&[String]` | `&` | Slice reference to a vector of strings. Efficient iteration. |
| `double` | `f64` | `owned` | Primitive type, no ownership |
| `int` | `i32` | `owned` | Primitive type, no ownership |
| `std::chrono::milliseconds` | `Duration` | `owned` | Rust duration types are used for time intervals. |
| `std::map<CacheKey, LogicalEntity>` | `std::sync::Mutex<std::collections::HashMap<CacheKey, LogicalEntity>>` | `Arc<Mutex<>>` | Thread-safe cache storage using a HashMap wrapped in a Mutex. |
| `std::map<std::string, YamlDataLoader::RouteData>` | `std::sync::Arc<std::collections::HashMap<String, RouteData>>` | `Arc` | Concurrent access requires thread-safe reference counting |
| `std::mutex` | `std::sync::Mutex` | `Arc<Mutex<>>` | Mutex for thread-safe access to shared data. |
| `std::ostringstream` | `std::ostringstream` | `owned` | Rust's std::ostringstream can be used for string formatting |
| `std::regex` | `regex::Regex` | `Arc<Regex>` | Regex compilation is expensive. Compile once and share via Arc or static Lazy. In Rust, use the `regex` crate. |
| `std::set<std::string>` | `HashSet<String>` | `owned` | Rust hash sets are heap-allocated and owned. |
| `std::shared_ptr<CacheTransactionContext>` | `CacheTransactionContext` | `owned` | C++ uses shared_ptr for RAII context, implying shared ownership or copyable context. In Rust, RAII is handled by stack allocation or explicit struct lifetime. Since it's a context wrapper, it likely holds a reference to a CacheManager. Use a struct that implements Drop for cleanup. |
| `std::string` | `String` | `owned` | Standard string type. Use String for owned data, &str for references. |
| `std::thread::sleep_for` | `thread::sleep` | `static` | Rust thread sleep is a static function. |
| `std::vector<Fare>` | `Vec<Fare>` | `owned` | Rust vectors are heap-allocated and owned. |
| `std::vector<Flight>` | `Vec<Flight>` | `owned` | Rust vectors are heap-allocated and owned. |
| `std::vector<std::string>` | `Vec<String>` | `owned` | Vector type remains same |
| `struct CacheStatistics` | `struct CacheStatistics` | `owned` | Direct translation of struct with public fields |

## 2. Ownership & Lifetime Patterns
| C++ Pattern | Rust Pattern | Rationale |
|-------------|--------------|-----------|
| DataLoader and YamlDataLoader | Box<dyn DataLoader> | Abstract over different data loading implementations |
| Heap allocated objects | Box<T> | Rust uses Box for heap allocation |
| Mutex-protected shared state | Arc<Mutex<>> | Arc provides thread-safe shared ownership, Mutex ensures exclusivity. |
| RAII CacheTransactionContext | Struct with Drop impl | C++ RAII manages transaction scope. Rust's Drop trait provides identical functionality automatically when the struct goes out of scope. No heap allocation needed unless the context holds complex state. |
| Raw pointers in std::map | Owned data in HashMap | Rust's HashMap uses owned data, ensuring memory safety. |
| References (&) | & | Rust uses references for borrowing |
| References to SearchResults | Result<SearchStatus, Error> | Return result instead of modifying by reference |
| Singleton instance | lazy_static::Lazy<CacheManager> | Rust's lazy_static provides a thread-safe singleton pattern. |
| Static Singleton Members (initialized_, totalSearches_, etc.) | static mut or OnceCell/AtomicUsize | C++ uses global static members for state. In Rust, static mut is unsafe. Use std::sync::OnceCell for lazy initialization of singletons or std::sync::atomic::AtomicUsize for counters if concurrent access is required. Given the current single-threaded assumption, a simple struct with interior mutability (RefCell) or a global OnceCell is preferred for safety. |
| Static variables (routes_, initialized_, etc) | Arc<Mutex<>> | Thread-safe access to shared state requires locking |
| Static variables (searchCount_, cacheHitCount_, etc) | Arc<Mutex<Statistics>> | Thread-safe access to shared counters |
| Value types with no pointers | Structs with owned fields | Rust structs directly map to C++ value types with owned data |
| const & | & | References in C++ map to references in Rust |
| global variable (CacheStatistics g_cacheStats) | static variable (static mut g_cacheStats: CacheStatistics) | Rust's static variables are thread-safe by default, but require unsafe operations for mutation |
| no smart pointers | direct usage of types | No ownership transfers needed for simple data structures |
| raw pointer | & | Raw pointers in C++ map to references in Rust |
| static std::vector<Flight> flights_; | static FLIGHTS: OnceLock<Mutex<Vec<Flight>>> = OnceLock::new(); | Rust requires explicit initialization and thread safety for static data. |
| std::exception catching | Result<T, E> propagation | C++ uses exceptions for control flow in error cases. Rust uses Result. The Orchestrator should return Result<SearchResults, OrchestratorError> or handle errors internally by returning a SearchResults with ERROR status, but the API should ideally expose failure via Result for better ergonomics. |
| std::string& | String | String in Rust is owned, so we take ownership |
| std::vector<Fare> filterFares(const SearchRequest& req) | fn filter_fares(req: &SearchRequest) -> Vec<Fare> | Rust references are used for immutable borrowing. |
| std::vector<Flight> filterFlights(const SearchRequest& req) | fn filter_flights(req: &SearchRequest) -> Vec<Flight> | Rust references are used for immutable borrowing. |

## 3. Error Handling (Exceptions -> Results)
| Module | Source (C++) | Recovery Strategy | Rust Pattern |
|--------|--------------|-------------------|--------------|
| **Cachemanager** | `CacheManager::get` | Return false on miss | `Result<bool, CacheError>` |
| **Cachemanager** | `CacheManager::put` | Return false on exception | `Result<bool, CacheError>` |
| **Cachemanager** | `CacheManager::invalidate` | Return false on non-existent key | `Result<bool, CacheError>` |
| **Cachemanager** | `CacheManager::toString` | Return empty string on error | `Result<String, CacheError>` |
| **Common** | `No explicit error handling in C++` | None | `Result<T, E> could be used for error handling if needed` |
| **Dataloader** | `bool DataLoader::init(const std::string& dataFile)` | returns false on failure | `Result<(), Box<dyn Error>>` |
| **Dataloader** | `bool DataLoader::loadFromFile(const std::string& filename)` | returns false on failure | `Result<(), Box<dyn Error>>` |
| **Dataloader** | `std::exception caught during price parsing` | LOG_WARNING and continue | `Result<(), Box<dyn Error>>` |
| **Datastructures** | `No explicit error handling in C++` | None | `Result<T, E> will be used for error handling in Rust implementation` |
| **Orchestrator** | `Orchestrator::initialize` | Returns false on failure, logs error. | `Result<bool, InitializationError>` |
| **Orchestrator** | `Orchestrator::validateRequest` | Returns false, caller creates error result. | `Result<(), ValidationError>` |
| **Orchestrator** | `SearchEngine::MP_Search` | Throws std::exception, caught and converted to SearchStatus::ERROR. | `Result<SearchResults, SearchEngineError>` |
| **Orchestrator** | `DataLoader::init` | Returns false on failure. | `Result<(), DataLoaderError>` |
| **Pricingengine** | `PricingException` | throw PricingException | `Result<T, Error>` |
| **Pricingengine** | `Invalid passenger count` | log warning and return 0.0 | `Result<T, Error>` |
| **Pricingengine** | `Invalid tax rate` | log warning and return | `Result<T, Error>` |
| **Pricingengine** | `Invalid booking fee` | log warning and return | `Result<T, Error>` |
| **Searchengine** | `std::exception` | Return Result with error | `Result<SearchStatus, Error>` |
| **Searchengine** | `PricingException` | Return Result with error | `Result<SearchStatus, Error>` |
| **Yamldataloader** | `YAML parsing errors` | Return false | `Result<T, E> where E = Box<dyn Error>>` |
| **Yamldataloader** | `File I/O errors` | Return false | `Result<T, E> where E = Box<dyn Error>>` |
| **Yamldataloader** | `Data validation errors` | Return false | `Result<T, E> where E = Box<dyn Error>>` |

## 4. Concurrency & Thread Safety
### Cachemanager
- **Thread Safety**: All cache operations are protected by a Mutex, ensuring thread-safe access.
- **Shared State**: `cache_`, `stats_`

### Common
- **Thread Safety**: Not thread-safe in C++, would require explicit synchronization in Rust
- **Shared State**: `g_cacheStats`

### Dataloader
- **Thread Safety**: DataLoader's static state must be accessed in a thread-safe manner using Rust's Mutex and OnceLock.
- **Shared State**: `FLIGHTS`, `FARES`, `INITIALIZED`, `LOAD_COUNT`

### Datastructures
- **Thread Safety**: All types are single-threaded with no shared state

### Orchestrator
- **Thread Safety**: Currently not thread-safe due to static mutable state. Rust migration should introduce std::sync::Mutex or std::sync::RwLock around shared state if multi-threading is required, or use thread-local storage if appropriate.
- **Shared State**: `initialized_`, `totalSearches_`, `successfulSearches_`, `errorSearches_`, `totalProcessingTimeMs_`, `CacheManager instance`

### Pricingengine
- **Thread Safety**: Not thread-safe, no synchronization primitives used
- **Shared State**: `taxRate_`, `bookingFee_`, `pricingCount_`

### Searchengine
- **Thread Safety**: Functions are not thread-safe
- **Shared State**: `searchCount_`, `cacheHitCount_`, `cacheMissCount_`

### Yamldataloader
- **Thread Safety**: Implementation uses Arc<Mutex<>> for thread-safe access to shared state
- **Shared State**: `routes_`, `initialized_`, `loadCount_`, `flightsFilePath_`, `faresFilePath_`

## 5. System Invariants
- **Cachemanager**: put(key, entity) followed by get(key) returns the same entity.
- **Cachemanager**: No key collisions; distinct SearchRequests map to distinct CacheKeys.
- **Cachemanager**: Thread-safe; concurrent get/put operations maintain data integrity.
- **Cachemanager**: Idempotent puts; putting the same key multiple times is safe.
- **Cachemanager**: Cache consistency; get() returns the exact copy of previously stored data.
- **Cachemanager**: No capacity limits or time-based expiration (simplified for POC).
- **Cachemanager**: No distributed caching or persistence (in-memory only).
- **Cachemanager**: All cache operations are atomic and consistent under concurrent access.
- **Common**: CacheStatistics must maintain accurate counts of hits, misses, puts, and invalidations
- **Common**: hitRate() must correctly compute hit rate as hits / (hits + misses)
- **Common**: g_cacheStats must remain a single global instance
- **Dataloader**: Every flight has at least one matching fare (by carrier and route)
- **Dataloader**: Same SearchRequest always returns the same LogicalEntity
- **Dataloader**: LogicalEntity contains only flights/fares that match the request
- **Dataloader**: All configured routes have at least one flight+fare combination
- **Dataloader**: Deterministic output from load_data() based on input
- **Dataloader**: No empty LogicalEntity is returned if a route is configured
- **Dataloader**: Data consistency is enforced via validate_data_consistency()
- **Dataloader**: Dataset is built deterministically via create_sample_dataset()
- **Datastructures**: SearchRequest must have non-empty origin, destination, and date
- **Datastructures**: Flight must have valid depTime <= arrTime
- **Datastructures**: Fare must have basePrice >= 0
- **Datastructures**: Itinerary legs must be non-empty if totalPrice > 0
- **Datastructures**: LogicalEntity must have non-empty flights or fares
- **Datastructures**: SearchResults itineraries must be sorted by price if sortByPrice called
- **Orchestrator**: initialized_ must be true before any search operation can succeed.
- **Orchestrator**: Statistics counters (totalSearches_, successfulSearches_, errorSearches_) must remain consistent with actual search outcomes.
- **Orchestrator**: CacheTransactionContext must ensure cache transaction integrity (commit/rollback) upon scope exit.
- **Orchestrator**: Request validation must enforce 3-letter uppercase airport codes and YYYY-MM-DD date format.
- **Orchestrator**: numPassengers must be between 1 and 9 inclusive.
- **Orchestrator**: Origin and Destination must not be identical.
- **Pricingengine**: Deterministic pricing: same inputs produce same output
- **Pricingengine**: Linear scaling: price for N passengers = N × (single passenger price)
- **Pricingengine**: Fare availability: every flight in itinerary must have a matching fare
- **Pricingengine**: Non-negative final price: all components are non-negative
- **Pricingengine**: Precision: monetary values are formatted to 2 decimal places
- **Searchengine**: maxItineraries_ must be > 0
- **Searchengine**: cacheHitCount_ + cacheMissCount_ == searchCount_
- **Yamldataloader**: After initialization, routes_ must contain valid data
- **Yamldataloader**: loadCount_ must be incremented on each loadData call
- **Yamldataloader**: fares and flights must have matching carriers

## 6. Module Function Contracts
### Cachemanager Module
#### `CacheManager::get`
- **Complexity**: O(log n)
- **Preconditions**:
  - key is valid
- **Postconditions**:
  - outEntity contains the cached LogicalEntity if found
- **Side Effects**:
  - Updates hit/miss statistics
#### `CacheManager::put`
- **Complexity**: O(log n)
- **Preconditions**:
  - key is valid
- **Postconditions**:
  - LogicalEntity is stored in cache
- **Side Effects**:
  - Updates statistics
#### `CacheManager::invalidate`
- **Complexity**: O(log n)
- **Preconditions**:
  - key is valid
- **Postconditions**:
  - Cache entry is removed if exists
- **Side Effects**:
  - Updates statistics
#### `CacheManager::clear`
- **Complexity**: O(1)
- **Postconditions**:
  - All cache entries are removed
- **Side Effects**:
  - Updates statistics
#### `CacheManager::contains`
- **Complexity**: O(log n)
- **Preconditions**:
  - key is valid
- **Postconditions**:
  - Returns true if key exists in cache
#### `CacheManager::size`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns the number of cache entries
#### `CacheManager::getStatistics`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns current cache statistics
#### `CacheManager::resetStatistics`
- **Complexity**: O(1)
- **Postconditions**:
  - Resets all statistics to zero
- **Side Effects**:
  - Updates statistics
#### `CacheManager::toString`
- **Complexity**: O(n)
- **Postconditions**:
  - Returns a string representation of the cache
#### `CacheManager::updateHitMissStats`
- **Complexity**: O(1)
- **Preconditions**:
  - hit is either true or false
- **Postconditions**:
  - Statistics are updated based on hit/miss
- **Side Effects**:
  - Updates statistics

### Common Module
#### `CacheAppTxnContext_Init`
- **Complexity**: O(1)
- **Postconditions**:
  - Logs initialization message
- **Side Effects**:
  - Writes to log
#### `CacheAppTxnContext_Quit`
- **Complexity**: O(1)
- **Postconditions**:
  - Logs termination message
- **Side Effects**:
  - Writes to log
#### `CacheStatistics::toString`
- **Complexity**: O(1)
- **Preconditions**:
  - Valid CacheStatistics instance
- **Postconditions**:
  - Returns formatted string with statistics

### Dataloader Module
#### `init`
- **Complexity**: O(n)
- **Preconditions**:
  - DataLoader must not be initialized
- **Postconditions**:
  - DataLoader is initialized or returns false
- **Side Effects**:
  - Static data initialization
#### `load_data`
- **Complexity**: O(n)
- **Preconditions**:
  - DataLoader must be initialized
- **Postconditions**:
  - Returns LogicalEntity with relevant flights and fares
- **Side Effects**:
  - Increments load count
#### `is_initialized`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns initialization status
#### `get_load_count`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns load count
#### `reset_load_count`
- **Complexity**: O(1)
- **Postconditions**:
  - Resets load count to 0
- **Side Effects**:
  - Modifies static state
#### `get_available_routes`
- **Complexity**: O(n)
- **Postconditions**:
  - Returns list of available routes
#### `get_dataset_summary`
- **Complexity**: O(n)
- **Postconditions**:
  - Returns dataset summary as string
#### `load_from_file`
- **Complexity**: O(n)
- **Preconditions**:
  - File must exist
- **Postconditions**:
  - Loads data from file or returns false
- **Side Effects**:
  - Modifies static state
#### `filter_flights`
- **Complexity**: O(n)
- **Postconditions**:
  - Returns filtered flights based on request
#### `filter_fares`
- **Complexity**: O(n)
- **Postconditions**:
  - Returns filtered fares based on request
#### `validate_data_consistency`
- **Complexity**: O(n^2)
- **Preconditions**:
  - DataLoader must be initialized
- **Postconditions**:
  - Returns true if data is consistent, false otherwise
#### `create_sample_dataset`
- **Complexity**: O(1)
- **Postconditions**:
  - Creates sample dataset
- **Side Effects**:
  - Modifies static state
#### `add_flights_for_route`
- **Complexity**: O(1)
- **Postconditions**:
  - Adds flights for given route
- **Side Effects**:
  - Modifies static state
#### `add_fares_for_route`
- **Complexity**: O(1)
- **Postconditions**:
  - Adds fares for given route
- **Side Effects**:
  - Modifies static state

### Datastructures Module
#### `SearchRequest::SearchRequest`
- **Complexity**: O(1)
- **Preconditions**:
  - orig, dest, dt are valid strings
  - pax >= 0
- **Postconditions**:
  - origin == orig
  - destination == dest
  - date == dt
  - num_passengers == pax
#### `SearchRequest::operator==`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if all fields are equal
#### `SearchRequest::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `Flight::Flight`
- **Complexity**: O(1)
- **Preconditions**:
  - All string parameters are valid
- **Postconditions**:
  - All fields initialized correctly
#### `Flight::operator==`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if all fields are equal
#### `Flight::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `Fare::Fare`
- **Complexity**: O(1)
- **Preconditions**:
  - All string parameters are valid
  - price >= 0
- **Postconditions**:
  - All fields initialized correctly
#### `Fare::operator==`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if all fields are equal
#### `Fare::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `Itinerary::Itinerary`
- **Complexity**: O(n) where n is number of legs
- **Preconditions**:
  - flightLegs is valid vector
- **Postconditions**:
  - legs initialized with flightLegs
  - totalPrice == 0.0
#### `Itinerary::addLeg`
- **Complexity**: O(1)
- **Postconditions**:
  - flight added to legs
#### `Itinerary::operator==`
- **Complexity**: O(n) where n is number of legs
- **Postconditions**:
  - Returns true if legs and totalPrice are equal
#### `Itinerary::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `CacheKey::CacheKey`
- **Complexity**: O(1)
- **Preconditions**:
  - orig, dest, dt are valid strings
  - pax >= 0
- **Postconditions**:
  - All fields initialized correctly
#### `CacheKey::fromRequest`
- **Complexity**: O(1)
- **Preconditions**:
  - req is valid SearchRequest
- **Postconditions**:
  - Returns CacheKey initialized from request fields
#### `CacheKey::operator==`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if all fields are equal
#### `CacheKey::operator<`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if fields are in order
#### `CacheKey::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `LogicalEntity::LogicalEntity`
- **Complexity**: O(n) where n is number of flights and fares
- **Preconditions**:
  - flts and frs are valid vectors
- **Postconditions**:
  - flights and fares initialized correctly
#### `LogicalEntity::isEmpty`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns true if flights or fares are empty
#### `LogicalEntity::getCombinationCount`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns product of flights and fares sizes
#### `LogicalEntity::operator==`
- **Complexity**: O(n) where n is number of flights and fares
- **Postconditions**:
  - Returns true if flights and fares are equal
#### `LogicalEntity::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string
#### `SearchResults::addItinerary`
- **Complexity**: O(1)
- **Preconditions**:
  - itin is valid Itinerary
- **Postconditions**:
  - itinerary added to itineraries
#### `SearchResults::sortByPrice`
- **Complexity**: O(n log n) where n is number of itineraries
- **Postconditions**:
  - itineraries sorted by totalPrice
- **Side Effects**:
  - Modifies itineraries order
#### `SearchResults::toString`
- **Complexity**: O(n) where n is string length
- **Postconditions**:
  - Returns properly formatted string

### Orchestrator Module
#### `performSearch`
- **Complexity**: O(1) logic overhead + O(N) search complexity depending on SearchEngine
- **Preconditions**:
  - Orchestrator must be initialized
  - Request must be valid
- **Postconditions**:
  - Returns SearchResults with status OK, NOT_FOUND, or ERROR
  - Statistics updated
- **Side Effects**:
  - Updates totalSearches_, successfulSearches_, errorSearches_, totalProcessingTimeMs_
  - Accesses CacheManager via CacheTransactionContext
#### `initialize`
- **Complexity**: O(1)
- **Preconditions**:
  - System not previously initialized
- **Postconditions**:
  - initialized_ set to true
  - DataLoader initialized
  - Statistics reset
- **Side Effects**:
  - Initializes DataLoader
  - Resets PricingEngine defaults
  - Resets Orchestrator statistics
#### `validateRequest`
- **Complexity**: O(L) where L is length of string fields (regex matching)
- **Preconditions**:
  - Request object exists
- **Postconditions**:
  - Returns true if request is valid, false otherwise
#### `warmUpCache`
- **Complexity**: O(K * T) where K is number of routes, T is time per search
- **Preconditions**:
  - Orchestrator initialized
  - Routes vector provided
- **Postconditions**:
  - Cache populated with results from performSearch
  - Returns count of new entries
- **Side Effects**:
  - Calls performSearch multiple times
  - Updates statistics for each search
#### `configure`
- **Complexity**: O(1)
- **Preconditions**:
  - System initialized (optional, but logically required for effect)
- **Postconditions**:
  - SearchEngine max itineraries set
  - PricingEngine tax/fee set
- **Side Effects**:
  - Updates global configuration in SearchEngine and PricingEngine

### Pricingengine Module
#### `computePrice`
- **Complexity**: O(n)
- **Preconditions**:
  - itin, entity, req are valid
- **Postconditions**:
  - returns total price
- **Side Effects**:
  - increments pricingCount_
#### `computePriceWithDetails`
- **Complexity**: O(n)
- **Preconditions**:
  - itin, entity, req are valid
- **Postconditions**:
  - returns total price and fills outDetails
- **Side Effects**:
  - increments pricingCount_
#### `setTaxRate`
- **Complexity**: O(1)
- **Preconditions**:
  - rate is valid (0.0-1.0)
- **Postconditions**:
  - taxRate_ is updated
- **Side Effects**:
  - logs change
#### `getTaxRate`
- **Complexity**: O(1)
- **Postconditions**:
  - returns current taxRate_
#### `setBookingFee`
- **Complexity**: O(1)
- **Preconditions**:
  - fee is valid (>=0)
- **Postconditions**:
  - bookingFee_ is updated
- **Side Effects**:
  - logs change
#### `getBookingFee`
- **Complexity**: O(1)
- **Postconditions**:
  - returns current bookingFee_
#### `resetToDefaults`
- **Complexity**: O(1)
- **Postconditions**:
  - taxRate_, bookingFee_, pricingCount_ are reset
- **Side Effects**:
  - logs reset
#### `getPricingCount`
- **Complexity**: O(1)
- **Postconditions**:
  - returns current pricingCount_
#### `resetPricingCount`
- **Complexity**: O(1)
- **Postconditions**:
  - pricingCount_ is reset
- **Side Effects**:
  - logs reset
#### `findMatchingFare`
- **Complexity**: O(n)
- **Preconditions**:
  - flight and fares are valid
- **Postconditions**:
  - returns matching Fare or null
- **Side Effects**:
  - throws PricingException if no match
#### `calculateTax`
- **Complexity**: O(1)
- **Preconditions**:
  - baseFare is valid
- **Postconditions**:
  - returns tax amount
#### `applyPassengerMultiplier`
- **Complexity**: O(1)
- **Preconditions**:
  - basePrice and numPassengers are valid
- **Postconditions**:
  - returns multiplied price
- **Side Effects**:
  - logs warning for invalid numPassengers

### Searchengine Module
#### `MP_Search`
- **Complexity**: O(n) where n is number of flights
- **Preconditions**:
  - SearchRequest must be valid
- **Postconditions**:
  - SearchResults contains valid data or error
- **Side Effects**:
  - Increments searchCount_
  - Updates cache statistics
#### `buildItineraries`
- **Complexity**: O(n) where n is number of flights
- **Preconditions**:
  - LogicalEntity contains valid flights
- **Postconditions**:
  - Returns valid list of Itineraries
- **Side Effects**:
  - Logs debug information
#### `priceItineraries`
- **Complexity**: O(n) where n is number of itineraries
- **Preconditions**:
  - Valid Itinerary list
- **Postconditions**:
  - Itineraries contain pricing information
- **Side Effects**:
  - Logs debug/error information
#### `sortByPrice`
- **Complexity**: O(n log n)
- **Preconditions**:
  - Valid Itinerary list
- **Postconditions**:
  - Itineraries sorted by price
- **Side Effects**:
  - Logs debug information
#### `limitResults`
- **Complexity**: O(1)
- **Preconditions**:
  - Valid Itinerary list
- **Postconditions**:
  - Itinerary list limited to maxItineraries_
- **Side Effects**:
  - Logs debug information

### Yamldataloader Module
#### `init`
- **Complexity**: O(n) where n is number of routes
- **Preconditions**:
  - flightsYaml and faresYaml are valid file paths
- **Postconditions**:
  - initialized_ is set to true if successful
- **Side Effects**:
  - Modifies static variables
#### `loadData`
- **Complexity**: O(n) where n is number of flights and fares
- **Preconditions**:
  - initialized_ must be true
- **Postconditions**:
  - Returns LogicalEntity with filtered data
- **Side Effects**:
  - Modifies loadCount_
#### `isInitialized`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns current initialization state
#### `getLoadCount`
- **Complexity**: O(1)
- **Postconditions**:
  - Returns current load count
#### `resetLoadCount`
- **Complexity**: O(1)
- **Postconditions**:
  - Resets load count to 0
- **Side Effects**:
  - Modifies loadCount_
#### `getAvailableRoutes`
- **Complexity**: O(n) where n is number of routes
- **Postconditions**:
  - Returns vector of route keys
#### `getDatasetSummary`
- **Complexity**: O(n) where n is number of routes
- **Postconditions**:
  - Returns string summary of dataset
#### `reloadData`
- **Complexity**: O(n) where n is number of routes
- **Preconditions**:
  - flightsFilePath_ and faresFilePath_ are set
- **Postconditions**:
  - Reloads data from YAML files
- **Side Effects**:
  - Modifies static variables
#### `updateFares`
- **Complexity**: O(n) where n is number of fares
- **Preconditions**:
  - initialized_ must be true
- **Postconditions**:
  - Updates fares for given route and date
- **Side Effects**:
  - Modifies routes_
#### `loadFlightsFromYaml`
- **Complexity**: O(n) where n is number of flights
- **Preconditions**:
  - filename is valid
- **Postconditions**:
  - Loads flights from YAML file
- **Side Effects**:
  - Modifies routes_
#### `loadFaresFromYaml`
- **Complexity**: O(n) where n is number of fares
- **Preconditions**:
  - filename is valid
- **Postconditions**:
  - Loads fares from YAML file
- **Side Effects**:
  - Modifies routes_
#### `parseFlightsFromRoute`
- **Complexity**: O(n) where n is number of flights
- **Preconditions**:
  - routeNode contains valid data
- **Postconditions**:
  - Parses flights from route node
- **Side Effects**:
  - Modifies routes_
#### `parseFaresFromRoute`
- **Complexity**: O(n) where n is number of fares
- **Preconditions**:
  - routeNode contains valid data
- **Postconditions**:
  - Parses fares from route node
- **Side Effects**:
  - Modifies routes_
#### `filterFlights`
- **Complexity**: O(n) where n is number of flights
- **Preconditions**:
  - SearchRequest is valid
- **Postconditions**:
  - Returns filtered flights
#### `filterFares`
- **Complexity**: O(n) where n is number of fares
- **Preconditions**:
  - SearchRequest is valid
- **Postconditions**:
  - Returns filtered fares
#### `validateDataConsistency`
- **Complexity**: O(n^2) where n is number of routes
- **Preconditions**:
  - routes_ contains loaded data
- **Postconditions**:
  - Validates dataset consistency
#### `makeRouteKey`
- **Complexity**: O(1)
- **Preconditions**:
  - origin and destination are valid
- **Postconditions**:
  - Returns route key string

