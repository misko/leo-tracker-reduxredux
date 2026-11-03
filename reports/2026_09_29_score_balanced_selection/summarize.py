from run import HERE, PARENT, load

if __name__ == "__main__":
    driver = load("summary_driver", PARENT / "summarize.py")
    driver.HERE = HERE
    driver.main()
