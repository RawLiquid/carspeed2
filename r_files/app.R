# install.packages("RPostgreSQL")
library(RPostgreSQL)
library(grid)
library(ggplot2)
library(gridExtra)
library(shiny)

# create a connection
# save the password that we can "hide" it as best as we can by collapsing it
pw <- {
  "Rward0232"
}

# loads the PostgreSQL driver
drv <- dbDriver("PostgreSQL")
# creates a connection to the postgres database
# note that "con" will be used later in each connection to the database
con <- dbConnect(drv, dbname = "speedcamdb",
                 host = "192.168.1.3", port = 5432,
                 user = "speedcam", password = pw)
rm(pw) # removes the password

# check for the cartable
dbExistsTable(con, "vehicles")

# Make sure there are no duplicate speeds in table (speeds are so precise, there should never be
# any real instances where they are the same)

remove_dupes <- "DELETE FROM vehicles
  WHERE id IN (SELECT id
  FROM (SELECT id,
  ROW_NUMBER() OVER (partition BY speed ORDER BY id) AS rnum
  FROM vehicles) t
  WHERE t.rnum > 1);"

ui <- fluidPage(
  titlePanel("Ridgmar Boulevard Speed Statistics"),
  
  sidebarLayout(
    sidebarPanel(
      sliderInput("obs", "Time Range", min = 10, max = 500, value = 100)
    ),
    mainPanel("main panel")
  )
)

server <- function(input, output) {
  # Send query
  dbGetQuery(con, remove_dupes)
  
  # query the data from postgreSQL 
  #vehicles <- dbGetQuery(con, "SELECT * from vehicles")
  
  vehicles <- vehicles[ which(vehicles$rating <= 5), ]  # Only keep good values
  vehicles <- vehicles[ which(vehicles$rating > 0), ]
  vehicles <- vehicles[ which(vehicles$speed <= 50), ]
  #vehicles <- vehicles[ which(vehicles$datetime >= Sys.time() - 14400), ]  # should subset past six hours
  median <- median(vehicles$speed)
  
  bar_plot <- ggplot(vehicles, aes(x = as.factor(as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H'))), 
                       y = vehicles$speed)) + geom_boxplot() + geom_hline(yintercept = 35, colour = "red") +
    geom_hline(yintercept = median, colour = "forestgreen") + xlab("Time") + ylab("Speed")
  
  loess <- ggplot(vehicles, aes(x = as.POSIXct(strptime(vehicles$datetime, '%Y-%m-%d %H:%M')), 
                       y = vehicles$speed)) + stat_smooth(level = .99) + geom_point() + xlab("Time") + ylab("Speed") +
    geom_hline(yintercept = 35, colour = "red") + geom_hline(yintercept = median, colour = "forestgreen")
  
  
  grid.arrange(bar_plot, loess, ncol=2, top=textGrob("Driver Speed on Ridgmar Boulevard", gp=gpar(fontsize=16)))

}

shinyApp(ui = ui, server = server)
